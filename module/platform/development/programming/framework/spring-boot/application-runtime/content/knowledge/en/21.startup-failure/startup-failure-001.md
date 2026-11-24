# Classifying Spring Boot Startup Failures: Before Context, During Refresh, and in Runners

## 1. Why classify failures by lifecycle phase?

When a Spring Boot application fails to start, the last log lines often contain **APPLICATION FAILED TO START**, **BeanCreationException**, **IllegalStateException**, or a message from an external library. If you only look at the exception name and fix by guesswork, it is very easy to treat the wrong cause.

A more useful diagnostic question is: **At the moment the error occurred, which lifecycle milestone had SpringApplication reached?**

In Spring Boot 3.5, there are three main groups to distinguish:

1. **Before ApplicationContext exists:** Boot is preparing the Environment, ConfigData, or running early hooks. No context or bean factory is ready yet to retrieve business beans.
2. **During ApplicationContext.refresh():** the context has been created and configuration sources have been loaded, but the container is parsing/registering BeanDefinitions, creating singleton beans, running lifecycle callbacks, or starting the embedded server.
3. **During ApplicationRunner/CommandLineRunner:** the context **has refreshed successfully** and Spring Boot has published **ApplicationStartedEvent**, but final startup work fails before **ApplicationReadyEvent**.

**Do not conflate these three groups.** Even though all of them appear as "startup failed", access to Environment, beans, DataSource, web server, failure analyzers, and remediation strategies differ across them.

### Three quick questions

- **Does the context exist yet?** If not, you cannot use a bean listener, repository, or @Autowired to handle it.
- **Has refresh completed yet?** If not, do not assume @Bean, @PostConstruct, post-processors, and required singletons are ready.
- **Have runners completed yet?** If not, the app may have already logged "Started" yet still not be considered ready.

This article uses **Spring Boot 3.5.x and Java 17+**. Event and API names are aligned with Spring Boot 3.5 documentation, not legacy event names from Boot 1.x versions.

## 2. Event milestone map

~~~text
main(String[] args)
      |
      v
SpringApplication.run(args)
      |
      +--> ApplicationStartingEvent
      |        No Environment / ApplicationContext yet
      |
      +--> Prepare Environment, ConfigData, active profiles...
      |        ApplicationEnvironmentPreparedEvent
      |        Environment ready, context NOT yet created
      |
      +--> Create ApplicationContext, run initializers
      |        ApplicationContextInitializedEvent
      |        Context created, primary sources not yet loaded
      |
      +--> Load initial BeanDefinition sources
      |        ApplicationPreparedEvent
      |        Context exists, NOT yet refreshed
      |
      +--> ApplicationContext.refresh()
      |        - configuration class processing
      |        - bean factory/bean post processors
      |        - @Configuration, @Bean, auto-configuration
      |        - initialize non-lazy singletons, @PostConstruct
      |        - embedded web server if web app
      |        ContextRefreshedEvent
      |
      +--> ApplicationStartedEvent
      |        Context refreshed, runners NOT yet invoked
      |        LivenessState.CORRECT
      |
      +--> ApplicationRunner / CommandLineRunner
      |        Seed, precondition checks, warm-up...
      |
      +--> ApplicationReadyEvent
      |        Runners completed normally
      |        ReadinessState.ACCEPTING_TRAFFIC
      |
      v
SpringApplication.run returns
~~~

**ApplicationFailedEvent** can be published when an exception causes startup to fail. It is **not** a milestone that only occurs after ApplicationReadyEvent: the failure event can appear in different phases depending on where the error originates.

**ContextRefreshedEvent** belongs to Spring Framework, while the **Application...Event** events in the diagram belong to Spring Boot. For a web application, **WebServerInitializedEvent** can also be published between Prepared and Started.

### Core classification table

| Signal | Before context | During refresh | In runner |
| --- | --- | --- | --- |
| **Environment** | May be prepared; uncertain if error occurred earlier | Yes | Yes |
| **ApplicationContext** | Does not exist yet | Exists, but refresh has not succeeded | Refreshed successfully |
| **ApplicationPreparedEvent** | No | Usually yes, if error is inside refresh | Yes |
| **ContextRefreshedEvent** | No | Usually no on failed refresh | Yes |
| **ApplicationStartedEvent** | No | No | **Yes** |
| **ApplicationReadyEvent** | No | No | **No** if runner throws |
| **Business beans** | Cannot rely on them yet | May be only partially created | Normally ready after refresh |
| **Primary investigation focus** | ConfigData, JVM/classpath, early listeners | Bean definitions, dependency injection, init, web server | Runner logic, runtime dependencies, transactions, timeouts |

The word **"usually"** is important: an exception can happen during **context creation before refresh**, which does not fit cleanly into just those three simple buckets. Section 7 explains this boundary case and how to avoid drawing wrong conclusions from a single event.

## 3. Group A — Failures before ApplicationContext exists

### 3.1. What does "context not yet created" mean?

Spring Boot must initialize several components **before** instantiating an ApplicationContext:

- Configuring SpringApplication and application arguments.
- Preparing the Environment.
- Locating and loading **application.properties/application.yml**, ConfigData imports, and profile-specific configuration.
- Running **EnvironmentPostProcessor** implementations and Environment-phase listeners.
- Determining the web application type and early startup options.

**ApplicationEnvironmentPreparedEvent** is published when the Environment has been prepared enough to inspect or modify, **before the context is created**. Therefore, a listener handling this event cannot do:

~~~java
context.getBean(MyService.class);
~~~

This is an **anti-pattern snippet**: there is no context variable and no business bean has been initialized by Spring at that point. If you need to read configuration, use **event.getEnvironment()** instead of forcing bean creation.

### 3.2. Common failures

| Symptom | Possible error source | What to check |
| --- | --- | --- |
| Cannot load required ConfigData import | Config file/location or config source does not exist | spring.config.import, location, optional:, and read permissions |
| Malformed YAML | YAML syntax, indentation, special characters | File and line number reported by the parser |
| Wrong active profile | CLI/env/profile group or config precedence | spring.profiles.active, environment variables, and profile-specific files |
| EnvironmentPostProcessor throws exception | Custom logic, missing resource | Postprocessor ordering and root cause stack trace |
| Failure during logging/config bootstrap | Classpath, version mismatch, early config | Dependency tree, JVM args, logging configuration |
| Very early ClassNotFound/NoClassDefFoundError | Missing dependency, incompatible bytecode | JVM version and libraries on the runtime classpath |
| Early listener reads a bean | Trying to access @Autowired/getBean before context exists | Switch extension point and use the Environment API |

**Not every property error belongs to the pre-context group.** For example, a malformed URL value may load into the Environment normally and only fail when bound to **@ConfigurationProperties** during refresh. Always classify by **when the error is actually thrown**, not merely because a class name relates to configuration.

### 3.3. Diagnosing before beans exist

Useful steps:

1. Check the **Java runtime/version, classpath, and actual launch command**.
2. Read the first meaningful exception and the deepest **Caused by**, not just the final top-level line.
3. Check where configuration is loaded from: filesystem, classpath, environment variables, command-line, config import.
4. For ConfigData errors, verify **paths, permissions, active profiles**, and property source ordering.
5. For EnvironmentPostProcessor, inspect class registration and its own dependencies without relying on DI business beans.
6. If you need a listener to record early milestones, register it via **SpringApplication.addListeners(...)** or an appropriate early registration mechanism instead of waiting for a @Bean in the context.

**One limitation:** if an error happens **before SpringApplication.run() is invoked** (for example, a main class static initializer fails, the JVM cannot load a class, the java command is wrong, or ClassNotFoundException occurs before entering Boot), Boot has no opportunity to dispatch ApplicationFailedEvent. That is a launch failure **outside** SpringApplication, even though to an operator the symptom is still "app won't start".

## 4. Group B — Failures during ApplicationContext.refresh()

### 4.1. What does refresh() do?

Once SpringApplication has created the ApplicationContext, run initializers, loaded primary sources, and published **ApplicationPreparedEvent**, the context enters **refresh()**. During this phase Spring:

- Prepares the BeanFactory and runs **BeanDefinitionRegistryPostProcessor** implementations.
- Parses **@Configuration**, **@ComponentScan**, **@Import**, **@Bean**, and applicable auto-configurations.
- Executes **BeanFactoryPostProcessor** implementations to adjust metadata.
- Registers **BeanPostProcessor** implementations (e.g., to support annotation injection and AOP proxies).
- Instantiates non-lazy singletons.
- Performs dependency injection, validation, initialization callbacks, and **@PostConstruct**.
- For web applications, creates/starts the embedded web server at the relevant points of refresh.
- When refresh succeeds, publishes **ContextRefreshedEvent**.

**A BeanDefinition being loaded does not mean the bean instance already exists.** A @Bean method may not have been invoked at ApplicationPreparedEvent and is only executed during refresh.

### 4.2. Common failure forms

| Exception/symptom | Likely cause | Approach |
| --- | --- | --- |
| **BeanCreationException** | @Bean factory method, constructor, or init method threw an error | Find the bean name, creation method, and root cause |
| **UnsatisfiedDependencyException** | Required dependency is missing or could not be created | Check constructor parameters, component scan, profiles |
| **NoSuchBeanDefinitionException** | Required bean type/name was not registered | Check starter, @Component/@Bean, @Conditional |
| **NoUniqueBeanDefinitionException** | Multiple candidates for an injection point | Use @Qualifier/@Primary or redesign |
| **BeanCurrentlyInCreationException** | Unresolvable circular dependency | Break the dependency cycle; do not just re-enable circular refs |
| **BeanDefinitionStoreException** | Corrupted configuration metadata | Check config source/scan and class metadata |
| **BindException / validation errors** | @ConfigurationProperties failed binding or validation | Check property names, types, @Validated, and constraints |
| **PortInUseException** | Embedded server cannot bind port | Check process occupying port, server.port, and deployment |
| **NoSuchMethodError/LinkageError** | Incompatible libraries | Inspect dependency graph/BOM and runtime versions |
| Error in **@PostConstruct** | Init callback uses DB/API too early or misconfigured | Move long-running tasks to a runner when appropriate |

The exception names in the table are **common examples**, not a one-to-one mapping between exception class and lifecycle phase. For instance, the same **IllegalStateException** can be thrown in refresh or in a runner depending on the code. **The stack trace and lifecycle events** are what distinguish them.

### 4.3. Signals confirming refresh did not succeed

- **ApplicationPreparedEvent** occurred, but **ApplicationStartedEvent** has not been seen.
- The stack trace leads into **AbstractApplicationContext.refresh**, BeanFactory, configuration parser, constructor, or @Bean factory method.
- A specific bean name appears in **BeanCreationException**.
- For a web app, logs show the embedded server initializing, then failing to bind or start.
- **ApplicationFailedEvent** may be published with a created context; however, the context may already be closing during error handling.

**Do not infer that just because the log says "Tomcat initialized", refresh has completed.** The web server can partially initialize and then fail. The **ApplicationStartedEvent** milestone is a clearer indicator that SpringApplication got past refresh successfully.

### 4.4. Lazy initialization shifts when errors surface

If you enable:

~~~properties
spring.main.lazy-initialization=true
~~~

many beans are created lazily on demand. A broken dependency or factory method may not fail during startup; the error only surfaces on the first request or when a runner actively calls getBean.

Therefore, **do not equate "startup succeeded" with all beans having been verified**. When debugging, inspect the scope of lazy beans and exercise real business paths. However, do not arbitrarily disable lazy initialization in production just to force eager initialization of every resource too early.

## 5. Group C — Failures in ApplicationRunner or CommandLineRunner

### 5.1. When do runners execute?

Spring Boot invokes **ApplicationRunner** and **CommandLineRunner** beans after ApplicationContext refresh succeeds, after **ApplicationStartedEvent**, and before **ApplicationReadyEvent**.

~~~text
ContextRefreshedEvent
       |
       v
ApplicationStartedEvent
       |
       v
Runner begins
       |
       +--> succeeds --> Next runner (if any)
       |                      |
       |                      v
       |               ApplicationReadyEvent
       |
       +--> throws --> ApplicationFailedEvent
                       Normal ready event not published
~~~

A consequence that is very easy to overlook:

**The log "Started ... in X seconds" or ApplicationStartedEvent does not mean the application is ready.** Boot still has to run runners before declaring readiness.

Tasks commonly placed in runners:

- Seeding default data.
- Warming up caches.
- Validating critical configuration or connectivity to external systems.
- Loading indexes/mappings required before serving traffic.
- Running short startup operations with explicit timeouts and error policies.

### 5.2. Common failures

| Failure | Why it usually only appears in a runner | Remediation |
| --- | --- | --- |
| External DB/API temporarily unavailable | Runner is where live connections/validation run | Timeouts, bounded retry/backoff, fail vs degraded policy |
| Seed data hits duplicate key | Startup/redeploy or multiple replicas running same logic | Unique constraint, insert-if-absent, idempotency |
| Runner queries unmigrated table | Wrong migration order or schema drift | Ensure migration runs before the runner |
| Cache warm-up exceeds deadline | Large query, slow network, invalid data | Batching, bounded timeout, required/best-effort policy |
| Business logic exception | Null/IllegalState in runner code | Inspect root cause and inputs |
| Runner returns early while Future still runs | Boot only waits for the run() call to return | Await required tasks and fail explicitly |
| Wrong multi-runner ordering | Runner B assumes A already ran | @Order/Ordered or an explicit coordinator |
| Transaction failure | Transaction boundary or non-idempotent retry | Extract @Transactional service, verify commit/rollback |

### 5.3. When a runner throws, has the context already refreshed successfully?

**Yes, in normal Spring Boot startup.** Runners are called **after** ApplicationStartedEvent, meaning refresh is complete. An exception in a runner causes **SpringApplication.run(...) to fail** and triggers Boot's cleanup/context closing, so the instance can no longer be treated as ready.

A controller in a web app **may already have an open port** before the runner fails. Do not use a LISTEN port to conclude the service is ready. Use a proper readiness probe to avoid routing traffic while mandatory runners have not finished.

### 5.4. Do not fake success with a catch-all

Dangerous pattern:

~~~java
@Override
public void run(ApplicationArguments args) {
    try {
        mandatorySeed();
    } catch (Exception ignored) {
        // Wrong if this data is a mandatory requirement.
    }
}
~~~

This is an **anti-pattern snippet** with `mandatorySeed` undefined. It can cause Boot to publish **ApplicationReadyEvent** even though seeding failed.

How to handle failures depends on policy:

- **Required startup task:** use bounded retries for transient errors, then throw an exception and let startup fail if requirements are still unmet.
- **Best-effort optimization:** log clearly, record metrics, and allow fallback, without introducing bad data into the system.
- **Asynchronous task:** only return before completion if your readiness policy has its own tracking mechanism; Boot does not automatically wait for every CompletableFuture created by a runner.

**@Transactional** in a runner does not guarantee that side effects outside the database roll back with the transaction. For emails, messaging, or external APIs, use idempotency keys or outbox/durable job state as required.

## 6. What is ApplicationFailedEvent and what are its limits?

**ApplicationFailedEvent** is the event Spring Boot publishes when startup fails. It provides:

- **getException()**: the Throwable that caused startup to fail.
- **getApplicationContext()**: the context being created/started, **which can be null** if the error occurred before the context existed.
- SpringApplication and raw arguments information from the superclass.

Example snippet inside a listener:

~~~java
if (event instanceof ApplicationFailedEvent failed) {
    Throwable failure = failed.getException();
    boolean contextWasCreated =
            failed.getApplicationContext() != null;

    System.err.println(
            "contextPresent=" + contextWasCreated);
    System.err.println(
            "exceptionType=" + failure.getClass().getName());
}
~~~

This is a **listener snippet** requiring the `event` variable and appropriate imports. Do not call **failed.getApplicationContext().getBean(...)** when the context may be null, unrefreshed, or closing.

### Register listeners early enough

If a listener exists only as a **@Bean** or **@Component**, it may not have been created yet when a pre-context or refresh failure occurs. To observe **ApplicationEnvironmentPreparedEvent** and very early failures, register via **SpringApplication.addListeners(...)** before calling run.

Do not put `@EventListener` on a business bean and conclude an event was not published simply because the bean did not exist yet. **When the listener is registered** determines whether it can receive early events.

### ApplicationFailedEvent is not a JVM-wide catch-all

If the JVM fails to load the main class, a class initializer dies before SpringApplication.run begins, or the process receives SIGKILL, Boot may **not publish ApplicationFailedEvent**. Some very early errors in initializing SpringApplication/listeners also bypass normal failure handling. Treat it as a diagnostic signal **once Boot is coordinating startup**, not an omnipotent log.

### FailureAnalyzer and event listeners are different

**FailureAnalyzer** analyzes a Throwable to produce a helpful **Description** and **Action** for operators. Spring Boot ships many built-in analyzers, such as for port-in-use errors or common configuration issues.

**ApplicationFailedEvent listener** receives an event to observe/log; it does not automatically turn a Throwable into a cause-and-action report. An analyzer might not recognize your custom error; in that case logging the stack trace is usually necessary.

It is not recommended for a listener to throw a new exception while handling a failure event because doing so can mask the original error. When logging, do not print secrets from the Environment or stack traces containing credentials.

## 7. The boundary zone: context created but not yet refreshed

The three groups in this article are the **primary classification axis**, but Spring Boot has an intermediate span between **before context** and **refresh**:

~~~text
ApplicationEnvironmentPreparedEvent
    |
    +--> SpringApplication creates ApplicationContext
    |
    +--> ApplicationContextInitializer callbacks
    |
    +--> ApplicationContextInitializedEvent
    |
    +--> Load primary sources
    |
    +--> ApplicationPreparedEvent
    |
    v
refresh() starts
~~~

If an **ApplicationContextInitializer** throws an exception, the failure **no longer belongs strictly to "before context"** because the context has been created, yet it **does not belong to refresh either**. Likewise, errors while loading primary sources or in a listener handling ApplicationPreparedEvent can happen **before refresh begins**.

Therefore, technical reports should use more precise labels when needed:

- **PRE_CONTEXT**: ApplicationContext not yet created.
- **CONTEXT_PREPARE**: context exists, before refresh.
- **REFRESH**: container is refreshing, not yet completed.
- **RUNNER**: context refreshed, executing startup runners.
- **POST_READY_RUNTIME**: startup finished; errors while serving requests or running background tasks are not SpringApplication.run failures.

**Do not use "ApplicationPreparedEvent occurred" to infer that beans have been initialized.** That event only indicates the context and initial source definitions have been loaded, not refreshed.

A helpful measurement combines **the last successful milestone**, **stack trace**, **root cause**, and if available **ApplicationFailedEvent.getApplicationContext()**. A single signal is not enough to classify every failure.

## 8. Complete Java 17+ example: triggering failures at all three milestones in one project

The following program runs on **Spring Boot 3.5.x** and **Java 17+**, without needing a web server. You pass **--demo.fail-at=...** to intentionally trigger a failure at one of three places:

- **before-context**: ApplicationEnvironmentPreparedEvent listener throws IllegalStateException before ApplicationContext exists.
- **refresh**: SampleService `@Bean` method throws IllegalStateException while Spring initializes singletons.
- **runner**: ApplicationRunner throws IllegalStateException after ApplicationStartedEvent has been published.
- **none**: starts successfully as a baseline for comparison.

This is a **lab that intentionally throws exceptions**. Do not copy failure-triggering flags into production.

### 8.1. Create the project and POM

Use Maven and Java 17+, project package **com.example.demo**. Complete POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>startup-failure-lab</artifactId>
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

**Explanation:** spring-boot-starter is enough for SpringApplication, ApplicationRunner, bean factory, and events. You do not need starter-web, JDBC, or Actuator because the goal is startup failure classification.

If your environment uses another 3.5.x patch version, you can adjust the **parent version** according to the corresponding BOM. Do not arbitrarily mix Spring Framework JARs from versions incompatible with Boot.

### 8.2. The application.properties file

Create **src/main/resources/application.properties**:

~~~properties
spring.application.name=startup-failure-lab
spring.main.web-application-type=none

# Do not fail when running without a CLI override:
demo.fail-at=none
~~~

The project runs non-web to avoid noise from port binding. The **demo.fail-at** property is specific to this exercise and is **not** a standard Spring Boot property.

### 8.3. Complete Java file

Create **src/main/java/com/example/demo/StartupFailureLabApplication.java**:

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupFailureLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupFailureLabApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);

        // Register BEFORE run to receive very early events.
        application.addListeners(new TraceListener());
        application.run(args);
    }

    @Bean
    SampleService sampleService(Environment environment) {
        System.out.println("04 BEAN_FACTORY");

        if ("refresh".equals(
                environment.getProperty("demo.fail-at", "none"))) {
            System.out.println("FAIL_REFRESH");
            throw new IllegalStateException(
                    "simulated failure during context refresh");
        }

        return new SampleService();
    }

    @Bean
    ApplicationRunner startupRunner(
            Environment environment, SampleService service) {

        return args -> {
            System.out.println(
                    "07 RUNNER_BEGIN service=" + service.name());

            if ("runner".equals(
                    environment.getProperty("demo.fail-at", "none"))) {
                System.out.println("FAIL_RUNNER");
                throw new IllegalStateException(
                        "simulated failure in ApplicationRunner");
            }

            System.out.println("08 RUNNER_DONE");
        };
    }

    static final class SampleService {
        String name() {
            return "ok";
        }
    }

    static final class TraceListener
            implements ApplicationListener<ApplicationEvent> {

        @Override
        public void onApplicationEvent(ApplicationEvent event) {

            if (event instanceof ApplicationEnvironmentPreparedEvent e) {
                System.out.println("01 ENV_READY");

                String mode = e.getEnvironment().getProperty(
                        "demo.fail-at", "none");

                if ("before-context".equals(mode)) {
                    System.out.println("FAIL_BEFORE_CONTEXT");
                    throw new IllegalStateException(
                            "simulated failure before context");
                }

            } else if (event instanceof ApplicationContextInitializedEvent) {
                System.out.println("02 CONTEXT_INITIALIZED");

            } else if (event instanceof ApplicationPreparedEvent) {
                System.out.println("03 CONTEXT_PREPARED");

            } else if (event instanceof ContextRefreshedEvent) {
                System.out.println("05 CONTEXT_REFRESHED");

            } else if (event instanceof ApplicationStartedEvent) {
                System.out.println("06 APPLICATION_STARTED");

            } else if (event instanceof ApplicationReadyEvent) {
                System.out.println("09 APPLICATION_READY");

            } else if (event instanceof ApplicationFailedEvent e) {
                System.out.println("EVENT_FAILED contextPresent="
                        + (e.getApplicationContext() != null));
            }
        }
    }
}
~~~

**Points to check in the code:**

- Public class, package, and file name match; no Java API newer than Java 17 is used.
- **ApplicationListener<ApplicationEvent>** receives event subclasses; **instanceof pattern matching** is valid from Java 16+.
- The listener is instantiated with **new TraceListener()** and registered **before run**; it does not depend on component scan.
- **ApplicationEnvironmentPreparedEvent.getEnvironment()** accesses the CLI property **--demo.fail-at** before the context exists.
- **@Bean SampleService** is a default non-lazy singleton called during refresh; exceptions here are typically wrapped by Spring in **BeanCreationException**.
- **ApplicationRunner** is created as a bean during refresh, but its **run method** is invoked **after ApplicationStartedEvent**.
- **SampleService** injected into the runner proves beans are ready; no repository or web server is needed.
- **ApplicationFailedEvent.getApplicationContext()** is null-checked before use; we do not attempt to get beans from a potentially failed or closing context.
- The program prints fixed markers; exception stack traces and Spring Boot log lines also depend on the environment.

### 8.4. Build

From the project root directory:

~~~bash
java -version
mvn -version
mvn clean package
~~~

If the project was generated with Maven Wrapper from Initializr, you can run **./mvnw clean package** (Linux/macOS) or **.\mvnw.cmd clean package** (Windows PowerShell/cmd). With the POM above, the executable JAR is:

~~~text
target/startup-failure-lab-0.0.1-SNAPSHOT.jar
~~~

If you change artifactId/version, update the actual JAR name accordingly.

### 8.5. Testing each phase

**No failure:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=none
~~~

Application markers on a successful startup:

~~~text
01 ENV_READY
02 CONTEXT_INITIALIZED
03 CONTEXT_PREPARED
04 BEAN_FACTORY
05 CONTEXT_REFRESHED
06 APPLICATION_STARTED
07 RUNNER_BEGIN service=ok
08 RUNNER_DONE
09 APPLICATION_READY
~~~

These are **marker lines printed by the example itself**, not the entire stdout (Spring Boot also prints INFO logs). For this non-web project, after a successful run the JVM can exit because no web server keeps the process alive; that is not a startup failure.

**Group A — failure before context:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=before-context
~~~

Markers reflecting where the error is thrown:

~~~text
01 ENV_READY
FAIL_BEFORE_CONTEXT
EVENT_FAILED contextPresent=false
~~~

Key takeaway: Environment exists, context has not been created so **contextPresent=false**; there is no CONTEXT_INITIALIZED, PREPARED, or RUNNER_BEGIN. If an error occurs even before SpringApplication.run, EVENT_FAILED might not even appear.

**Group B — failure during refresh:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=refresh
~~~

Expected markers:

~~~text
01 ENV_READY
02 CONTEXT_INITIALIZED
03 CONTEXT_PREPARED
04 BEAN_FACTORY
FAIL_REFRESH
EVENT_FAILED contextPresent=true
~~~

Key takeaway: Context was created and Prepared was published. The bean factory method threw an exception while creating the singleton, so **ContextRefreshedEvent** and **ApplicationStartedEvent** have not occurred. The top-level exception may be BeanCreationException, while the root cause is the demo's IllegalStateException.

**Group C — failure in runner:**

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar --demo.fail-at=runner
~~~

Expected markers:

~~~text
01 ENV_READY
02 CONTEXT_INITIALIZED
03 CONTEXT_PREPARED
04 BEAN_FACTORY
05 CONTEXT_REFRESHED
06 APPLICATION_STARTED
07 RUNNER_BEGIN service=ok
FAIL_RUNNER
EVENT_FAILED contextPresent=true
~~~

Key takeaway: Refresh and ApplicationStartedEvent completed, but **ApplicationReadyEvent is not published** because the runner failed.

The output blocks above focus only on the **example's System.out markers**; error logs, stack traces, ANSI colors, and interleaving between stdout/stderr may vary. When multiple threads or loggers write concurrently, do not rely on ordering between stdout and stderr as sole evidence. On normal error paths produced by the example, the java process exits unsuccessfully; observe the exact exit code in your shell/runtime.

### 8.6. Running all four cases with a script

Bash example (Linux/macOS or WSL) if you want to compare quickly:

~~~bash
for mode in none before-context refresh runner; do
  echo "==================== $mode"
  java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar \
    --demo.fail-at="$mode" || echo "Startup failed for $mode"
done
~~~

This command **intentionally triggers exceptions** in three runs. Do not run it against production services, load benchmarks, or pipelines unaware that the exit code will fail.

### 8.7. Adapting the exercise to recognize real-world errors

Once you understand the three markers, you can replace the explicit IllegalStateException throws with controlled realistic failures:

- Before context: configure **spring.config.import** pointing to a missing resource without `optional:`.
- During refresh: create a bean requiring an unregistered mandatory dependency.
- In runner: invoke a seed service with a simulated error or timeout.

Do **not** try to trigger failures by deleting production data, shutting down shared databases, or corrupting real secrets. Use a local test profile, H2/Testcontainers, or appropriate mock services.

## 9. Quick diagnostic decision table by last seen milestone

| Last milestone observed | Can be inferred | Must not be inferred | Action |
| --- | --- | --- | --- |
| No Boot events at all | Possible very early error or missing logging | That Spring was definitely never called | Check java command, JVM, classpath, and stderr |
| ENV_READY, contextPresent=false | Error before context creation in example | That every property error is pre-context | Check ConfigData, early hooks, config sources |
| CONTEXT_INITIALIZED but no PREPARED | Inside context preparation/loading sources | That refresh completed | Check initializer, registry/source loading, listeners |
| CONTEXT_PREPARED but no REFRESHED | Near/inside refresh, possible listener failure at Prepared | That all beans were created | Inspect actual phase in stack trace |
| BEAN_FACTORY + FAIL_REFRESH | Error right when @Bean method creates singleton | Failure in runner | Inspect bean factory, @PostConstruct, root cause |
| CONTEXT_REFRESHED, APPLICATION_STARTED | Refresh succeeded | That the application is ready | Check runners and runner ordering |
| RUNNER_BEGIN then EVENT_FAILED | Runner failed (in demo) | That auto-configuration needs fixing | Inspect business startup task, network, transaction |
| APPLICATION_READY | Boot completed runners along normal flow | That all dependencies stay healthy forever or requests never fail | Inspect readiness probes and runtime errors if any |

**Do not rely on marker numbering to draw conclusions in a project with custom listeners or an asynchronous event multicaster.** The demo creates one simple listener using default synchronous event behavior for clarity. In multi-context systems, events can repeat across parent/child contexts and the listener must verify the relevant context.

## 10. Dissecting stack traces in the right place

A failure during refresh may look like:

~~~text
BeanCreationException: Error creating bean with name 'sampleService'
    ...
Caused by: IllegalStateException:
    simulated failure during context refresh
~~~

This is an **illustrative excerpt**, not a full stack trace; class names, packages, method frames, and logger formatting vary by runtime. Here, **BeanCreationException is the container wrapper**, while the IllegalStateException thrown by the bean creation method is the direct cause.

A runner failure may be wrapped by Spring Boot with a message about executing ApplicationRunner:

~~~text
... Failed to execute ApplicationRunner
Caused by: IllegalStateException:
    simulated failure in ApplicationRunner
~~~

You do not need an exact character-for-character match on the wrapper message across patch versions. What matters is that **ApplicationStartedEvent occurred before the error** and the stack trace enters **startupRunner.run(...)**.

### Rules for reading the cause

1. Find the exception near the top of the failure block to see where the framework reported the error.
2. Identify the relevant **bean name, runner class, property name, config location**, or port.
3. Follow **Caused by** to the most actionable error instead of stopping at a generic BeanCreationException.
4. Cross-reference with the last lifecycle milestone reached.
5. Only then decide whether to fix Spring configuration, dependencies, classpath, database, or business logic.

**Do not automatically pick the deepest cause in every failure** if the framework already provided a FailureAnalysis pinpointing the issue more accurately. Combine Spring's contextual message with the technical cause in the stack trace.

## 11. FailureAnalyzer, --debug, and the Condition Evaluation Report

Spring Boot provides the **FailureAnalyzer** mechanism to turn certain startup exceptions into actionable **Description** and **Action** sections. For example, when a port is already in use, Boot can output a report:

~~~text
APPLICATION FAILED TO START

Description:
Embedded web server cannot bind the configured port.

Action:
Stop the process using that port or choose another port.
~~~

This is an **informational illustration**, not a verbatim message guaranteed across every patch version or every embedded server.

### When to add --debug?

~~~bash
java -jar target/startup-failure-lab-0.0.1-SNAPSHOT.jar \
  --demo.fail-at=refresh --debug
~~~

**--debug** instructs Boot to output condition evaluation details useful for auto-configuration, depending on when the failure occurred and whether the context exists.

- If a bean was not created due to **@ConditionalOnClass**, **@ConditionalOnBean**, or **@ConditionalOnProperty**, the report can show matched/negative conditions.
- If the error occurred **before the context existed**, do not expect a complete Condition Evaluation Report.
- If the error is in runner code or a remote API, the auto-configuration report may not hold the primary cause.
- Enabling debug can generate very large logs and expose environment details in real systems; choose a safe logging scope.

You can configure targeted logging:

~~~properties
logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

This property can help inspect auto-configuration decisions, but it is not a magic fix. For apps failing before logging initializes, rely on stderr/JVM startup diagnostics and appropriate early logging mechanisms.

### Which phase does PortInUseException belong to?

With Spring MVC embedded Tomcat, port binding usually happens during context refresh/web server initialization. Therefore, port-in-use errors typically belong to **REFRESH**, not RUNNER. Always inspect the actual **stack trace and web server factory**; do not lump all network errors into runners.

## 12. Startup failure, liveness, and readiness

Spring Boot 3.5 defines:

~~~text
After ApplicationStartedEvent:
    LivenessState.CORRECT

After ApplicationReadyEvent:
    ReadinessState.ACCEPTING_TRAFFIC
~~~

For **pre-context** or **refresh** errors, the app never reaches Started. For **runner** errors, the context has refreshed and liveness state may already be CORRECT, but startup **has not reached Ready** and Boot enters failure handling.

This explains why:

- "Container process has a PID" does not mean the app is ready.
- "HTTP port is LISTENING" does not mean runners have finished.
- "Log contains Started..." does not mean ApplicationReadyEvent was published.
- A proper readiness probe must reflect the condition under which the app can serve real traffic.
- When startup fails, Kubernetes may restart the container due to process exit; a readiness probe is not a mechanism to fix startup errors.

**Do not force AvailabilityChangeEvent to publish ACCEPTING_TRAFFIC to mask a failing mandatory runner.** It does not fix the database or schema and can route traffic to an unready service.

If runner work is purely a performance optimization, you can offload it as best-effort background work with fallbacks and metrics, while clearly defining **what ready means** so orchestration is not misled.

## 13. Choosing the right hook to avoid placing failures in the wrong phase

| Need | Appropriate hook | Notes |
| --- | --- | --- |
| Add a PropertySource early | EnvironmentPostProcessor | Do not inject business beans; consider ConfigData ordering |
| Configure context before refresh | ApplicationContextInitializer | Context exists, but beans are not ready yet |
| Register/transform BeanDefinitions | BeanDefinitionRegistryPostProcessor | Runs in refresh; requires understanding registry lifecycle |
| Modify bean metadata | BeanFactoryPostProcessor | Avoid premature bean instantiation outside contract |
| Lightweight bean initialization | Constructor/@PostConstruct | Avoid slow network calls unless necessary |
| Run startup task needing Spring services | ApplicationRunner/CommandLineRunner | After refresh, before ready; needs idempotency |
| Receive ApplicationEnvironmentPreparedEvent | addListeners or early listener registration | Do not use a @Bean listener created too late |
| React after app is ready | ApplicationReadyEvent listener | Does not alter the fact that startup runners finished |
| Measure startup failures | ApplicationFailedEvent listener or FailureAnalyzer | Register at the right time; check context for null |
| Optional background work | Managed executor/scheduler with failure policy | Do not assume Boot waits for async tasks to finish |

Choosing the wrong hook causes hard-to-trace bugs: fetching a DataSource in EnvironmentPreparedEvent, calling a repository in @PostConstruct before dependencies are ready, or launching mandatory work in a Future and returning from the runner before it finishes.

## 14. When a failure occurs in a runner: retry, rollback, and idempotency

A realistic scenario: a runner seeds catalog data, writes 3/5 records, and hits a connection error. Kubernetes restarts the Pod and the runner runs again. Without unique constraints or durable state, duplicate records can be created.

Proper design:

- Each seed operation has a **stable business key** and a database unique constraint.
- Use insert-if-absent or upsert with well-defined semantics instead of unconditionally overwriting valid data.
- When seeding multiple related tables, choose proper transaction boundaries and ensure retries are idempotent.
- When calling external APIs, use an idempotency key or durable job/outbox if the target supports it.
- Retry only transient errors with bounded attempts, deadlines, backoff, and jitter.
- For permanent configuration errors such as a missing table due to migration, **fail fast** and fix the deployment instead of retrying endlessly.
- Log stage, elapsed time, attempt, and root cause without logging secrets.

**An ApplicationRunner throwing an exception fails startup, but it does not automatically roll back previously committed side effects.** SpringApplication failure handling can close the context, but it cannot undo a sent email or an already committed DB transaction.

With **@Transactional**, make sure calls go through the Spring proxy or use TransactionTemplate when needed; self-invocation may not start a transaction as intended.

## 15. Why not just delete a bean or disable a feature to make the app start?

Risky "quick fixes" include:

- Deleting a failing @Bean without understanding which services depend on it.
- Enabling spring.main.lazy-initialization=true merely to defer the failure until the first request.
- Catching and ignoring all Exceptions in a mandatory runner.
- Disabling readiness checks so the Pod reports READY while the DB/schema is still broken.
- Increasing timeouts to infinity to hide deadlocks or network connections lacking retry policies.
- Changing multiple library versions at once, obscuring binary incompatibilities.
- Reading one line "Error creating bean" and immediately altering component scan when the root cause is a wrong secret or database credential.

A better approach is to **narrow down the error by lifecycle**, reproduce it with a minimal configuration, find the root cause, and fix it at the appropriate extension point. Keep a regression test for the scenario that caused the failure.

## 16. Production scenarios: three incidents, three investigation paths

### Scenario 1 — Config server or ConfigData unavailable

The application does not get past the Environment phase. No context exists, so repositories and business listeners cannot rescue startup. Check **spring.config.import**, optional imports, config-reading credentials, and environment processing logs. If the config is mandatory, failing early is right. If optional, declare optional explicitly and define defaults.

### Scenario 2 — DataSource bean or web server fails during refresh

The context exists, but refresh has not succeeded. For DataSource, check driver, JDBC URL, credentials, bean construction, and database reachability; for port bind, check server.port and processes occupying the port. Enable debug to inspect the auto-config condition report **if helpful**, then trace BeanCreationException and the root cause.

### Scenario 3 — Cache warm-up throws an error in a runner

The context has refreshed and SpringApplication has started. The runner's database query times out. Decide whether the cache is **required** or **best effort**:

- Required: runner waits with a deadline, applies sensible retries, then fails startup if requirements are unmet.
- Best effort: record metrics, allow cache-aside/fallback, and become ready to accept requests.
- Do not leave a failing Future running in the background while letting Boot report ready if it is a mandatory requirement.

Each scenario shares the external symptom "process startup failed", yet has a different technical cause and recovery path.

## 17. Testing and observing failures by environment

### For unit and integration tests

- Test **EnvironmentPostProcessor** in a minimal configuration environment without loading the full ApplicationContext if unnecessary.
- Use **ApplicationContextRunner** for auto-configuration/bean condition tests; it does not necessarily publish the full SpringApplication event sequence of a real application.
- Use **SpringApplication** with an early-registered listener as in the demo to test event ordering.
- Use **@SpringBootTest** when the full context is needed; remember that context caching can prevent startup behavior from re-running on every test method.
- Test runner logic via a separate service and fake dependencies, then write an integration test verifying that exceptions actually cause startup to fail.

### For containers/Kubernetes

- Inspect **container exit reason/exit code**, logs, and previous logs when a container restarts repeatedly.
- Distinguish between process failing to start, startupProbe failure, livenessProbe restarts, and readinessProbe not yet healthy.
- Check timestamps between event markers and error stacks.
- Verify config from actual ConfigMaps, Secrets, environment variables, and command-line arguments.
- For slow startups, configure startupProbe appropriately; do not turn a permanent schema error into an infinite wait loop.
- At high replica counts, all pods seeding/warming up simultaneously can overload downstream services. Use idempotency, limits, and coordination.

### Suggested information to log

A clean startup log might contain:

~~~text
stage=ENVIRONMENT_PREPARED
stage=CONTEXT_PREPARED
stage=REFRESH_COMPLETED
stage=RUNNER_STARTED task=seed-defaults
stage=RUNNER_FAILED task=seed-defaults error=database-timeout
stage=APPLICATION_FAILED
~~~

This is a **log design pattern**, not default output from Spring Boot or the demo. Include **app version, environment, instance ID, elapsed time, trace/correlation ID** where appropriate. Avoid printing passwords, access tokens, JDBC URLs containing secrets, or sensitive config file contents.

## 18. Self-check exercises

**Q1.** Is ApplicationEnvironmentPreparedEvent published before or after ApplicationContext exists? Can a business repository be called directly inside its listener?

**Q2.** An application has ApplicationPreparedEvent but no ContextRefreshedEvent yet. What can you conclude, and what remains uncertain?

**Q3.** Boot published ApplicationStartedEvent and then a runner threw IllegalStateException. Will ApplicationReadyEvent occur? Has the app refreshed yet?

**Q4.** Can the same IllegalStateException name appear in all three groups? Why is exception type alone insufficient?

**Q5.** A @Bean factory method calls an external API and throws an error. Which phase does the failure belong to if the singleton is created during refresh?

**Q6.** An ApplicationContextInitializer throws an exception after the context is created. Does it belong strictly to "before context" or "during refresh"?

**Q7.** Why might a listener declared as @Component fail to receive errors during the Environment phase?

**Q8.** The app logs Started and port 8080 is open, yet readiness is not UP. Could this be because a runner is still executing?

**Q9.** Why is --debug/Condition Evaluation Report useful for @ConditionalOnBean but less helpful for a network error in a runner?

**Q10.** A runner seeds data partially and fails; can you assume SpringApplication automatically rolls back all prior writes?

**Q11.** An error occurs before SpringApplication.run because the main class cannot be loaded. Should you expect ApplicationFailedEvent?

**Q12.** Does enabling lazy initialization eliminate bean creation errors, or can it merely defer them to another time?

### Suggested answers

1. Before; there is no context/beans to use a repository.
2. Context is prepared, refresh is not confirmed complete; the error may occur before or during refresh.
3. No Ready event under the failed startup flow; refresh has completed.
4. Yes; throw site and lifecycle determine the phase.
5. Usually REFRESH, even though the underlying error comes from a remote API.
6. It is the CONTEXT_PREPARE span—context exists, but refresh has not started.
7. Because bean listeners are created after early events; use addListeners before run.
8. Yes; ApplicationStartedEvent and an open port do not equate to Ready.
9. The conditions report describes auto-configuration, not every remote runtime timeout.
10. No; you need transactions, unique keys, idempotency, and recovery.
11. No; the failure lies outside SpringApplication startup handling.
12. It may defer the failure until the bean is first used; it does not make a broken configuration valid.

## 19. Pre-fix diagnostic checklist

- [ ] Do you know which **Spring Boot/JDK** version the startup actually runs on?
- [ ] Have you verified the failing instance's command-line, profiles, ConfigData, and env vars?
- [ ] Have you recorded the **last successful lifecycle milestone**?
- [ ] Have you distinguished PRE_CONTEXT, CONTEXT_PREPARE, REFRESH, RUNNER, and post-Ready runtime?
- [ ] Have you read **Caused by** and the most actionable error message?
- [ ] When there is no context yet, are you avoiding @Autowired/getBean?
- [ ] For refresh errors, have you checked BeanCreation/DI/validation/port bind?
- [ ] For runner errors, have you checked transactions, retries, seed idempotency, and external services?
- [ ] Are you avoiding mistaking ApplicationStartedEvent for ApplicationReadyEvent?
- [ ] Are you avoiding treating an open port as proof the app is ready to serve?
- [ ] Have you avoided catching and ignoring Exceptions in mandatory startup tasks?
- [ ] Is --debug/Condition Evaluation Report used only when appropriate?
- [ ] Have you tested failure/restart and protected data against duplicate side effects?
- [ ] Have you set bounded timeouts and logged sufficient details without exposing secrets?
- [ ] Have you checked that the context failure event may have a null context and avoided mutating a closed context?

## 20. Summary and official sources

**The most reliable classification combines event milestones, context state, and stack trace:**

~~~text
BEFORE CONTEXT:
  Environment/config/early hook fails
  -> no context yet, do not use beans

DURING REFRESH:
  @Configuration / BeanDefinition / singleton / web server fails
  -> context exists, but no ApplicationStartedEvent yet

IN RUNNER:
  Context refreshed, ApplicationStartedEvent occurred
  -> runner fails, never reaches ApplicationReadyEvent

Outside the three groups:
  Failures during context preparation before refresh
  and failures outside SpringApplication.run / after ready
~~~

**ApplicationFailedEvent** helps observe startup failures but does not replace root cause analysis; **FailureAnalyzer** can provide Description/Action for supported errors. For mandatory tasks before ready, use runners with proper timeouts, retries, and idempotency rather than catch-all blocks that falsely report the system healthy.

Official documentation references for Spring Boot 3.5:

1. Spring Boot 3.5 Reference — SpringApplication, Application Events and Listeners, Startup Failure, runners: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Boot 3.5 API — ApplicationFailedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html
3. Spring Boot 3.5 API — ApplicationEnvironmentPreparedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationEnvironmentPreparedEvent.html
4. Spring Boot 3.5 API — ApplicationPreparedEvent: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/event/ApplicationPreparedEvent.html
5. Spring Boot 3.5 API — FailureAnalyzer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/diagnostics/FailureAnalyzer.html
6. Spring Framework Reference — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html

Examples are designed for **Spring Boot 3.5.x, Java 17+, and Maven**. On other versions, check the JavaDoc of the exact deployed version before building runbooks around event ordering, diagnostics, and auto-configuration.