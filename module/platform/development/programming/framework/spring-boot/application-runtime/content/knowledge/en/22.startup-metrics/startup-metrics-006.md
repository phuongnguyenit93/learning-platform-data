# FlightRecorderApplicationStartup and Integration with Java Flight Recorder in Spring Boot

## 1. The Problem to Solve: Where Is the Application Slow to Start?

A Spring Boot application may need several seconds, tens of seconds, or longer to reach readiness. That time covers many tasks: loading Java classes, preparing configuration, scanning packages, parsing `@Configuration`, registering BeanDefinitions, instantiating singleton beans, establishing connections, starting the embedded web server, and executing startup runners.

When startup time increases, a log line like **Started Application in 8.4 seconds** only reports the overall result. It cannot answer:

- How much time was spent by **Spring scanning packages**?
- Which bean **initializes slowly**?
- Is the JVM busy with **class loading, JIT compilation, garbage collection**?
- Is Spring executing business code or waiting on **database, network, file I/O**?
- Is a slow startup step slow because it itself burns CPU, or because it was hit by a **GC pause**/blocked I/O while running?
- If one bean is optimized, does overall application startup actually become faster?

Spring Framework provides **ApplicationStartup** and **StartupStep** to mark steps inside the container. One implementation is **FlightRecorderApplicationStartup**, responsible for emitting Spring startup steps as **Java Flight Recorder (JFR) events**. By recording Spring events **in the same JFR session** as JVM events, we can correlate **what Spring is doing** with **what the JVM is experiencing**.

**Key takeaway:** FlightRecorderApplicationStartup describes instrumented Spring startup steps; Java Flight Recorder adds JVM and runtime traces. Both layers of data complement each other in a single **.jfr** file for startup time analysis.

This lesson is based on **Java 17+**, **Spring Boot 3.5.x**, and **Spring Framework 6.2.x**. The core APIs belong to Spring Framework, not a required Spring Boot Actuator dependency.

## 2. Distinguishing Three Closely Related Concepts

| Component | Belongs to | Responsibility |
| --- | --- | --- |
| **ApplicationStartup** | Spring Framework, package **org.springframework.core.metrics** | Abstraction to start and end startup steps |
| **StartupStep** | Spring Framework | Object recording name, id, parent id, tags, and end time of a step |
| **FlightRecorderApplicationStartup** | Spring Framework, package **org.springframework.core.metrics.jfr** | Implementation of ApplicationStartup exporting StartupStep as JFR events |
| **Java Flight Recorder (JFR)** | JDK/JVM | Records timestamped/duration events related to JVM, OS, and custom events |
| **JDK Mission Control (JMC)** | JFR analysis tool, installed separately when needed | Visual UI to open .jfr files and inspect timelines/profiling |
| **BufferingApplicationStartup** | Spring Boot | Stores StartupSteps in a buffer, which can back the Actuator startup endpoint |

**ApplicationStartup is not a JVM profiler.** It measures steps marked by Spring or application code. **JFR does not automatically understand beans, @Configuration, and context refresh** without Spring instrumentation or another event mechanism providing that semantics.

By default, Spring Framework uses the no-op **ApplicationStartup.DEFAULT** implementation to avoid step-recording overhead when no specific tracker is enabled. To get Spring startup events in JFR, you must **configure FlightRecorderApplicationStartup before Spring initializes the context** and **enable a JFR recording early enough**.

### Does Java Flight Recorder Require a Separate Maven Library?

**No** for common JDK 17+ distributions that include JFR. JFR is built into supported JDKs. In Spring Boot 3.5, **spring-core** is already on the classpath via standard starters, so **FlightRecorderApplicationStartup does not require adding an external JFR library**.

What to distinguish:

- **JVM/JDK** provides flight recording.
- **Spring Framework** provides FlightRecorderApplicationStartup.
- **JDK Mission Control** is a separate tool to view and analyze recordings, not necessarily bundled with the JDK.
- **Spring Boot Actuator** is not needed to record startup steps into JFR.

## 3. How Does StartupStep Work?

Each **StartupStep** marks a unit of work:

~~~text
ApplicationStartup.start("demo.catalog.initialize")
                |
                +--> creates StartupStep
                |    name, id, parentId
                |
                +--> tag("component", "catalog")
                |
                +--> performs work
                |
                +--> step.end()
                       |
                       +--> finishes measuring step
                       +--> JFR event can be committed
~~~

Typically, step names follow a dot-separated namespace:

- **spring.context.refresh**
- **spring.beans.instantiate**
- **spring.context.config-classes.parse**
- **demo.catalog.initialize**
- **demo.runner.validate**

Names starting with **spring.** are reserved by Spring Framework for internal instrumentation. When writing custom steps, choose your own namespace such as **demo.**, **app.**, or a module name; do not place custom steps under **spring.***.

Basic interface usage:

~~~java
ApplicationStartup startup = /* a configured instance */;
StartupStep step = startup.start("demo.catalog.initialize");
step.tag("component", "catalog");
try {
    // Initialize application data.
} finally {
    step.end();
}
~~~

This is an **illustrative code fragment**, not a standalone Java file; imports, the `startup` variable, and middle logic are required. In the complete program in section 7, Spring injects the configured **ApplicationStartup**.

### Why Must end() Be Called?

When **start(...)** is called, the step begins being measured. The **end()** method signals that the work finished and lets the implementation record the result. With FlightRecorderApplicationStartup, the corresponding JFR event is committed when the step completes according to the recording mechanism.

**Do not forget end() if an exception occurs.** Use try/finally to avoid losing information when initialization fails:

~~~java
StartupStep step = startup.start("demo.external-config.load");
try {
    loadConfig();
} finally {
    step.end();
}
~~~

This fragment assumes `startup` and `loadConfig` exist; the key part is **finally**. If an operation throws an error, the step is still ended and JFR gets a chance to record its duration. However, **whether the .jfr file gets written to disk on JVM exit/failure** also depends on how the recording was started, dumponexit, disk/quota, and the type of JVM failure.

### Tags and JFR Limitations

**StartupStep.tag(key, value)** adds useful classification metadata: bean name, module, source, or operation type. FlightRecorderApplicationStartup serializes tags into **a String attribute** because JFR event fields only support types compatible with its format.

Do not put into tags:

- Passwords, tokens, connection strings containing secrets.
- Request payloads or personal data.
- Large JSON payloads.
- Excessively high-cardinality IDs with no analytical value.
- A dump of the entire Environment or System Properties.

Tags are primarily for identifying **the step and context**, not for business logging or distributed tracing storage.

## 4. Spring Steps That Can Be Instrumented

Spring Framework 6.2 lists core-container startup steps. Common examples:

| Startup step | Meaning |
| --- | --- |
| **spring.context.refresh** | ApplicationContext refresh phase |
| **spring.context.base-packages.scan** | Scanning base packages |
| **spring.context.config-classes.parse** | Parsing configuration classes |
| **spring.context.config-classes.enhance** | CGLIB enhancement of @Configuration when needed |
| **spring.context.beandef-registry.post-process** | Running BeanDefinitionRegistryPostProcessor |
| **spring.context.bean-factory.post-process** | Running BeanFactoryPostProcessor |
| **spring.context.beans.post-process** | Bean post-processing phase |
| **spring.beans.instantiate** | Instantiating a bean and its dependencies |
| **spring.beans.smart-initialize** | SmartInitializingSingleton callbacks |

These are **example step names in Spring Framework 6.2**, not a guarantee every recording has all steps in every application. Names and tags of internal startup steps **are not part of a stable public API contract**; they can change across patch/major versions.

**A single bean can appear multiple times across related steps**, and time intervals can overlap. Do not sum all durations by name and conclude that is total startup time. Parent steps can include the time of child steps.

To identify a slow bean, examine **beanName/beanType tags when recorded**, ordering/timeline, duration, and the dependency graph. A bean that looks slow may be waiting on another bean or a remote service, so use JFR JVM events and additional logs to verify.

## 5. Startup Order: Placing Instrumentation at the Right Time

In Spring Boot 3.5, a typical startup:

~~~text
main(String[] args)
      |
      +--> Create SpringApplication
      |
      +--> setApplicationStartup(
      |        new FlightRecorderApplicationStartup())
      |        MUST HAPPEN BEFORE run()
      |
      +--> SpringApplication.run(args)
      |        |
      |        +--> Environment / ConfigData preparation
      |        +--> Create and prepare ApplicationContext
      |        +--> Load bean definitions
      |        +--> Context refresh
      |        |      Bean factory, config parsing, singleton init,
      |        |      web server if web app
      |        +--> ApplicationStartedEvent
      |        +--> ApplicationRunner/CommandLineRunner
      |        +--> ApplicationReadyEvent
      |
      +--> run() returns if startup succeeds
~~~

**ApplicationStartup** itself is not an application event. It is an **instrumentation strategy** used by SpringApplication and ApplicationContext to mark multiple steps. Events such as **ApplicationStartedEvent** and **ApplicationReadyEvent** have their own lifecycle meaning; they do not automatically correspond one-to-one to a StartupStep with the same name.

Placing FlightRecorderApplicationStartup inside a **@Bean** created during refresh is usually **too late** to measure Environment, context preparation, and the earliest steps. The clearest approach:

~~~java
SpringApplication app =
        new SpringApplication(MyApplication.class);

app.setApplicationStartup(
        new FlightRecorderApplicationStartup());

app.run(args);
~~~

This is an illustrative snippet; `MyApplication` is your application class, with required imports. The static **SpringApplication.run(MyApplication.class, args)** is convenient, yet gives no hook to inject `setApplicationStartup` onto the instance before running; switch to instance-based `SpringApplication` when JFR startup tracking is needed.

### Distinguishing Startup Time from Readiness

**ApplicationStartedEvent** occurs after refresh, before runners. **ApplicationReadyEvent** occurs after runners complete. Therefore:

- Context refresh time differs from readiness-to-receive-traffic time.
- A custom step inside ApplicationRunner can be a major portion of startup.
- A runner creating a background Future and returning immediately **does not guarantee** Spring Boot waits for the Future before Ready.
- If mandatory warm-up work is unfinished, the application should not be called ready merely because beans were created.
- JFR can help highlight runner cost if you mark an appropriate custom StartupStep; do not assume every operation inside a runner automatically has a corresponding fine-grained step.

## 6. Starting JFR Properly So Startup Is Not Missed

### 6.1. Enable JFR at JVM Launch

Java 17+ example:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true \
  -jar target/jfr-startup-demo-0.0.1-SNAPSHOT.jar
~~~

**-XX:StartFlightRecording** is a JVM option, so it **must come before -jar**. Placing the option after the JAR name causes Spring Boot to treat it as an application argument, failing to enable JFR as intended.

Parameter explanations:

| Parameter | Effect |
| --- | --- |
| **filename=startup.jfr** | Output recording file path, relative to current working directory |
| **settings=profile** | Uses the JFR profiling configuration, usually recording more events than default |
| **dumponexit=true** | Dumps recording when the JVM exits via a normal shutdown path |
| **duration=15s** (optional) | Caps recording duration at about 15 seconds if the JVM keeps running |
| **delay=...** (if used) | Delays recording start; unsuitable when measuring startup from the very beginning |

Example for a long-running web application:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,duration=30s \
  -jar target/your-service.jar
~~~

The second command is a **template**; replace `your-service.jar` with the real JAR. The file is created when the recording ends after `duration`, if the JVM/recording writes successfully. Use `duration=30s` only if 30 seconds suffices to cover the startup you want to observe; for longer cold starts, increase duration or use dumponexit/explicit dump mechanisms.

**Important note:** if you start JFR after the application has finished starting via `jcmd`, you **cannot record startup events that already happened in the past**. To measure cold startup, enable recording from JVM launch or before the steps you want to measure.

### 6.2. Why Use settings=profile?

The JDK ships prebuilt recording configurations such as **default** and **profile**:

- **default:** suited for continuous recordings with relatively low overhead.
- **profile:** collects extra information for profiling, useful when investigating CPU, allocations, GC, and wait times.

Actual event coverage depends on the JDK version and `.jfc` settings. **Not every JVM event is enabled out of the box**; you may need to enable specific events/thresholds with a tailored JFR configuration.

For systems sensitive to overhead and storage, benchmark recording cost before enabling `profile` across all replicas. Use file rotation, size/age caps, and an appropriate retention policy.

### 6.3. Do You Need a JDK Instead of a JRE?

JFR is implemented in modern JDK runtimes, yet CLI utilities such as **jfr**, **jcmd**, and **jstack** are usually in the **full JDK**. A minimal container image or custom `jlink` image might lack those CLI tools.

In that case, you can record **startup.jfr** from the JVM in the container and then **copy the file to a machine with a full JDK** to run **jfr summary/print**, or open it with JDK Mission Control.

## 7. Complete Maven Example: Spring Boot 3.5 + FlightRecorderApplicationStartup

Example goals:

1. Run on **Java 17+**, without a web server.
2. Configure **FlightRecorderApplicationStartup before SpringApplication.run**.
3. Have a `@Bean` building catalog data and marking **demo.catalog.initialize**.
4. Have an `ApplicationRunner` validating data and marking **demo.runner.validate**.
5. Allow the program to exit normally so **dumponexit=true** can write the `.jfr` file.
6. Use `jfr summary/print` to find Spring steps and compare them with JVM events.

### 7.1. Project Structure

~~~text
jfr-startup-demo/
  pom.xml
  src/
    main/
      java/
        com/example/demo/JfrStartupDemoApplication.java
      resources/
        application.properties
~~~

If generated via Spring Initializr, the project also includes **mvnw** and **mvnw.cmd**. The example uses an installed Maven, needing no database, Spring Web, or Actuator.

### 7.2. Complete POM

Create **pom.xml**:

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
    <artifactId>jfr-startup-demo</artifactId>
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

**spring-boot-starter** suffices to bring in Spring Framework core, Spring Boot bootstrap APIs, and required dependencies. No separate "JFR starter" or `spring-boot-starter-actuator` dependency is needed for this exercise.

If using another Boot 3.5.x patch, update the parent/BOM version properly rather than overriding Spring Framework arbitrarily. Building the sample requires a Maven repository capable of supplying dependencies and JDK 17 or higher.

### 7.3. application.properties

Create **src/main/resources/application.properties**:

~~~properties
spring.application.name=jfr-startup-demo
spring.main.web-application-type=none

# No HTTP server or Actuator needed for JFR recording.
# Demo uses StartupSteps instrumented from Java code.
~~~

**There is no standard `spring.application-startup=flight-recorder` property** in Spring Boot 3.5 to replace the programmatic configuration in this lesson. Avoid guessing a property name and assuming instrumentation is active.

### 7.4. Complete Java File

Create **src/main/java/com/example/demo/JfrStartupDemoApplication.java**:

~~~java
package com.example.demo;

import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.metrics.ApplicationStartup;
import org.springframework.core.metrics.StartupStep;
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

@SpringBootApplication
public class JfrStartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(JfrStartupDemoApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        // Configure instrumentation BEFORE creating/refreshing context.
        app.setApplicationStartup(
                new FlightRecorderApplicationStartup());

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("RUN_RETURNED active="
                    + context.isActive());
        }
    }

    @Bean
    Catalog catalog(ApplicationStartup applicationStartup) {
        StartupStep step =
                applicationStartup.start("demo.catalog.initialize");
        step.tag("component", "catalog");
        System.out.println("CATALOG_BEGIN");

        try {
            // Simulate 300 ms initialization work.
            TimeUnit.MILLISECONDS.sleep(300);
            return new Catalog(3);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Catalog initialization interrupted", ex);
        } finally {
            step.end();
            System.out.println("CATALOG_END");
        }
    }

    @Bean
    ApplicationRunner warmupRunner(
            Catalog catalog, ApplicationStartup applicationStartup) {

        return args -> {
            StartupStep step =
                    applicationStartup.start("demo.runner.validate");
            step.tag("component", "runner");
            System.out.println("RUNNER_BEGIN items=" + catalog.items());

            try {
                // Simulate validation required before ApplicationReadyEvent.
                TimeUnit.MILLISECONDS.sleep(120);
                System.out.println("RUNNER_DONE");
            } finally {
                step.end();
            }
        };
    }

    record Catalog(int items) {
    }
}
~~~

### 7.5. Compilation Verification

- **package com.example.demo** matches the Java directory path.
- **JfrStartupDemoApplication** is a public class and matches the filename.
- **record Catalog(int items)** is Java 17, providing accessor **items()**.
- **FlightRecorderApplicationStartup** uses the exact package **org.springframework.core.metrics.jfr**.
- **ApplicationStartup** and **StartupStep** use the exact package **org.springframework.core.metrics**.
- **SpringApplication.setApplicationStartup(...)** is supported by Spring Boot 3.5.
- **ApplicationStartup** can be injected into Spring-managed components per the Spring Framework Reference.
- **StartupStep.start(...), tag(...), end()** match the Javadoc contract.
- **TimeUnit.MILLISECONDS.sleep(...)** can throw `InterruptedException`; the bean factory method catches and handles it, while **ApplicationRunner.run(ApplicationArguments)** declares **throws Exception** so the runner lambda can propagate `InterruptedException`.
- **try-with-resources** on `ConfigurableApplicationContext` is valid because it implements `Closeable`.
- The program requires no port 8080, database, scheduler, or Actuator.

**Important:** the `@Bean` method and the runner execute at different milestones. The `@Bean catalog` is created during context refresh, whereas **ApplicationRunner** is invoked only after refresh. The demo's custom steps reflect two genuinely distinct phases.

### 7.6. Build and Record JFR

From the project directory:

~~~bash
java -version
mvn -version
mvn clean package

java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true \
  -jar target/jfr-startup-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell/cmd: write the **java** command on **a single line** (do not use backslashes for line continuation). If using Maven Wrapper provided by Initializr, run **./mvnw clean package** on Linux/macOS or **.\mvnw.cmd clean package** on Windows.

Key stdout lines **printed by the application itself**:

~~~text
CATALOG_BEGIN
CATALOG_END
RUNNER_BEGIN items=3
RUNNER_DONE
RUN_RETURNED active=true
~~~

Maven/Boot/JFR may also emit other logs interleaved. These are only the application's markers, not a snapshot of the entire console. Sleep durations of 300 ms and 120 ms are simulated; actual event durations include small overhead and scheduler/JVM effects.

**Why does the program close its context automatically?** A non-web app does not need to run long-term in this example. When `SpringApplication.run` returns and exits **try-with-resources**, Java closes the `ApplicationContext`, `main` finishes, and JFR with **dumponexit=true** gets the chance to dump the recording to **startup.jfr**.

**Conditions for the file to exist:** runtime supports JFR, JVM options are accepted, target directory is writable, JVM can dump recording on exit, and the process is not forcibly killed before writing. Do not claim a `.jfr` file will appear under `SIGKILL` or out-of-disk-space conditions.

## 8. Analyzing the .jfr File with Built-in JDK Tools

### 8.1. Checking That the Recording Exists and Contains Data

After running the demo:

~~~bash
jfr summary startup.jfr
~~~

The JDK **jfr summary** command lists a summary of the recording, event counts by event type, and their recorded sizes. **Output will vary across JDKs, machines, startup conditions, and JFR configurations**, so no fixed numbers like byte size, GC count, or total startup duration are assumed.

In the summary, look for Spring's event group, typically named:

~~~text
org.springframework.core.metrics.jfr.FlightRecorderStartupEvent
~~~

You may also see events related to **jdk.Compilation**, **jdk.GarbageCollection**, **jdk.CPULoad**, **jdk.ClassLoad**, or many others depending on configuration and actual conditions.

**A JFR file containing the event type definition with zero instances does not prove the app created no steps.** Check whether the recording started early enough, the event is enabled in settings, `end` was called on the step, and whether threshold filters apply.

### 8.2. Filtering Startup Events Accurately

The event name of Spring Framework 6.2's implementation is:

~~~text
org.springframework.core.metrics.jfr.FlightRecorderStartupEvent
~~~

Use the fully qualified name:

~~~bash
jfr print --events org.springframework.core.metrics.jfr.FlightRecorderStartupEvent startup.jfr
~~~

To obtain JSON for tooling:

~~~bash
jfr print --json --events org.springframework.core.metrics.jfr.FlightRecorderStartupEvent startup.jfr
~~~

**Do not guess a name like `StartupEvent` and then conclude there is no data**. The **--events** filter must match the real event name in the file, not the `ApplicationStartup` interface name or the `SpringApplication` Java class name.

When in doubt, run:

~~~bash
jfr metadata startup.jfr
~~~

to inspect the actual event definitions in the recording. You can use **jfr summary** and search for Spring's name to avoid visually scanning the whole file.

**Version note:** if using a different Spring Framework version or another JFR instrumentation mechanism, event names may change. Rely on the metadata of the actual recording and the running code/version rather than hardcoding names from an arbitrary article.

### 8.3. Identifying Custom Steps

In the output of **jfr print**, look for the names:

~~~text
demo.catalog.initialize
demo.runner.validate
~~~

These two names are created by the demo itself, independent of which internal Spring steps are instrumented. With a successful recording and appropriate event settings, they confirm that the `FlightRecorderApplicationStartup` configuration took effect in application code.

**Do not hardcode JSON field names/value layouts in scripts without checking `jfr metadata` for your actual JDK and Spring version.** Tags may be serialized into strings, and JFR output formats timestamps/durations and metadata according to the tool.

### 8.4. Inspecting JVM Events to Find Root Causes

You can filter individual event types if present in the file:

~~~bash
jfr print --events jdk.GarbageCollection startup.jfr
jfr print --events jdk.CPULoad startup.jfr
jfr print --events jdk.ClassLoad startup.jfr
~~~

If an event type is disabled in `.jfc` settings or did not occur in the recording window, output may be empty. **Do not treat empty output as proof that the JVM had zero GC, zero CPU activity, or zero class loading**.

When diagnosing slow startup:

1. Find the `StartupStep` with a high duration.
2. Determine whether it encloses child steps.
3. Align that step's interval onto the JVM timeline.
4. Observe whether GC pauses, compilation, class loading, allocations, socket I/O, or thread waiting occurred in the same interval.
5. Inspect stack traces/sampling events when configured and present.
6. Reproduce multiple times to separate recurring issues from a single anomalous cold start.

**JFR correlation** is the main benefit: Spring tells **what it was doing**, and the JVM helps explain **why time passed**.

## 9. Opening the File with JDK Mission Control

**JDK Mission Control (JMC)** is a GUI tool for analyzing recordings. JMC is usually installed separately; do not assume every OpenJDK/JRE image includes it.

Workflow:

1. Open JDK Mission Control on a machine with a GUI environment.
2. Open **startup.jfr** using the open Flight Recording action.
3. Locate JFR events under the **Spring Application** category, labeled around **Startup Step**.
4. Filter events with step names **spring.context.refresh**, **spring.beans.instantiate**, **demo.catalog.initialize**, and **demo.runner.validate**.
5. Inspect **start time**, **duration**, **thread**, and metadata (if present).
6. Compare against JVM events such as **Garbage Collections**, **Threads**, **Class Loading**, and **Method Profiling**, depending on the JMC/JDK version.
7. Form a hypothesis, change exactly one likely cause, and record a new trace to compare.

Tab/menu names in JMC can change across versions. The essence is locating Spring's event category/names and opening the corresponding JVM timeline, not depending on a specific UI screenshot.

### How to Read a Hypothetical Scenario

Suppose a recording shows:

~~~text
demo.catalog.initialize       ~306 ms
demo.runner.validate          ~124 ms
spring.context.refresh        ~900 ms
jdk.GarbageCollection         ~120 ms during the same time
~~~

**These are illustrative figures**, not actual demo output. Analyze as follows:

- **demo.catalog.initialize** simulates a 300ms sleep; large duration does not prove busy CPU.
- **demo.runner.validate** simulates a 120ms sleep; likewise mostly waiting time.
- **spring.context.refresh** is a broad step that can enclose many child steps; **do not add 900 + 306** and treat it as a non-overlapping total.
- The 120ms GC, if it actually overlaps a startup step, can contribute to elapsed time; verify **timestamps and overlap**.
- To optimize, replace simulated sleep with real workload tracing, then re-measure under the same configuration and load.

### Why Can't You Compare Using Duration Alone?

Duration is the **wall-clock elapsed time** of the step interval, not a bean's isolated CPU metric. A 500 ms step can spend:

- 500 ms CPU.
- 5 ms CPU + 495 ms waiting on a database.
- 350 ms waiting on a monitor/thread lock.
- Some portion in a GC pause.
- Time waiting on I/O or external resources.

To conclude a bottleneck, you need additional JVM events and/or application logs/metrics over the same time window.

## 10. FlightRecorderApplicationStartup and BufferingApplicationStartup Differ

This is a notable configuration trap when reading Spring Boot docs.

| Characteristic | FlightRecorderApplicationStartup | BufferingApplicationStartup |
| --- | --- | --- |
| Provided by | **Spring Framework** | **Spring Boot** |
| Where data is stored | JFR recording session/file | In-memory buffer |
| Primary use | Profile and correlate with JVM events | Inspect startup steps via buffer/endpoint |
| Requires JVM JFR recording? | **Yes** to capture events to a .jfr file | No |
| Requires Spring Boot Actuator? | No | Only if HTTP startup endpoint is wanted |
| Output | JFR events with timestamps/duration/tags | Step data exportable as JSON via Actuator |
| Main risks | JFR started too late, missing settings, file/overhead | Insufficient buffer capacity, missing endpoint/exposure |
| Best suited for | Investigating slow startup and JVM-level root causes | Tracking step order/data and integrating observability tools |

Configuring BufferingApplicationStartup in Boot:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication app =
        new SpringApplication(MyApplication.class);

app.setApplicationStartup(
        new BufferingApplicationStartup(2048));

app.run(args);
~~~

This is an **illustrative Java fragment**, assuming `MyApplication` is already defined. Buffer capacity 2048 is only an example; choose based on actual startup step count and memory consumption.

### Does Actuator /actuator/startup Automatically Export a .jfr File?

**No.** The Actuator startup endpoint retrieves startup data from **BufferingApplicationStartup** via Boot's supported mechanism. Merely adding the Actuator dependency and enabling the endpoint does not mean the JVM wrote a `.jfr` file or that `FlightRecorderApplicationStartup` is active.

Conversely, when configuring `FlightRecorderApplicationStartup` as in this lesson, data goes to **JFR**, which does not mean **/actuator/startup** automatically contains an equivalent buffer.

SpringApplication accepts **one ApplicationStartup strategy at a time**. If you want both JFR and buffering, you must design and verify an appropriate composite/custom instrumentation solution; do not call `setApplicationStartup` twice in a row expecting both to work. The last `setApplicationStartup` call replaces the earlier one.

### When to Choose Which?

- **Want to see JVM GC, class loading, CPU profiling alongside Spring startup:** choose **FlightRecorderApplicationStartup + JFR**.
- **Want startup steps as JSON and Actuator integration:** consider **BufferingApplicationStartup** with an appropriate startup endpoint.
- **Only need total startup time:** use Spring Boot logs + ApplicationStarted/Ready metrics; enabling JFR is not strictly necessary.
- **Want continuous production analysis:** consider JFR default settings, bounded recordings, and dedicated security/retention policies.

## 11. Recording JFR with jcmd While the JVM Is Running

The JDK includes **jcmd** to manage Flight Recordings on a running JVM:

~~~bash
jcmd <PID> JFR.check
jcmd <PID> JFR.start name=investigate settings=profile
jcmd <PID> JFR.dump name=investigate filename=runtime.jfr
jcmd <PID> JFR.stop name=investigate
~~~

These commands are **CLI templates**: replace **<PID>** with the real PID. In Markdown, angle brackets are syntax placeholders; when running in a shell, type the **PID number**, e.g., `12345`, without angle brackets.

**Limitation:** if `jcmd` is invoked **after Spring Boot is already Ready**, the new runtime recording **will not contain StartupSteps emitted during earlier startup**. Thus, to study **startup measurement**, the default approach should be the JVM option **-XX:StartFlightRecording** right at process launch.

If you need to dump a running recording that was already enabled from the start:

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump filename=checkpoint.jfr
~~~

**12345** is a hypothetical PID to illustrate syntax. `jcmd` can be restricted by permissions, container namespaces, attach mechanisms, or JDK/runtime distributions. `jcmd` is not needed for the non-web demo because the program exits on its own with **dumponexit=true**.

### What If the JVM Exits Abnormally?

- **Process exit with normal shutdown hooks/dump:** usually gets a chance to write the file if configured.
- **SIGKILL, OOM-killer, force-killed container:** `dumponexit` is not guaranteed to run.
- **Read-only filesystem or full disk quota:** file writing can fail.
- **JFR disabled or unsupported runtime:** no event file as expected.

In environments where startup crashes are suspected, you can arrange early disk-backed JFR writing and appropriate collection mechanisms, without relying entirely on `dumponexit` to preserve data after a forced kill.

## 12. Optimizing After Finding the Bottleneck

JFR helps **form data-backed hypotheses**, yet changes must follow confirmed root causes.

### 12.1. Slow Due to Classpath and Configuration Scanning

If package scanning or configuration class parsing steps are large:

- Narrow **@ComponentScan** from scanning unnecessary scopes.
- Audit unused starters/auto-configurations.
- Measure class loading/JIT and context parsing phases.
- Avoid blindly disabling auto-configurations just because many beans appear; verify benefits and functional impact.

### 12.2. Slow Due to Bean Initialization

If **spring.beans.instantiate** or a custom bean step is slow:

- Identify `beanName` and dependency chain.
- Check constructors/`@PostConstruct` for blocking I/O.
- Evaluate remote config loading, DB validation, and data warm-up.
- Separate work truly required before ready from best-effort work.
- Set timeouts for I/O; never use infinite sleeps/retries.
- Do not just turn on lazy initialization to hide errors and push costs onto the first request.

### 12.3. Slow Due to JVM/JDK

If the timeline shows heavy GC, class loading, or JIT:

- Check heap size, CPU quota, container memory, and filesystem performance.
- Compare warm vs. cold start, page cache, JDK version, and GC configuration.
- Inspect JFR JVM events and profiling settings for your exact Java version.
- Do not conclude from a single run since JIT/classloading/OS scheduling vary across runs.

### 12.4. Slow Due to ApplicationRunner

If context refresh is fast yet Ready is slow:

- Measure the runner and seed tasks, cache warm-up, and dependency checks.
- For mandatory work, use bounded retries and deadlines.
- For deferrable work, consider background tasks with fallback and an appropriate readiness policy.
- Avoid runners submitting a `CompletableFuture` and returning before mandatory work finishes: Boot may announce Ready prematurely.

### 12.5. Slow Due to Network

If a custom step has high duration yet low CPU:

- Check DNS, TLS handshake, connect timeout, JDBC pool acquisition, and remote latency.
- Correlate with JFR socket events when settings support them.
- Add application-level instrumentation right at network call sites.
- Do not merely raise thread count: downstream connection pools or rate limits may be the actual bottleneck.

## 13. Startup Measurement Can Be Skewed by Inconsistent Experiment Design

A useful recording is not just a file created successfully. Before A/B comparisons:

1. Use the **same JDK version**, Spring Boot patch, classpath, and application.
2. Keep **CPU, RAM, container limits**, machine type, and storage comparable.
3. Document **cold/warm start**, file cache, and remote dependency state.
4. Keep **JFR settings** identical across both groups; `profile` recording can have different overhead than `default`.
5. Collect multiple runs; check median/p95 or distributions rather than picking one flattering number.
6. Distinguish **Spring startup step duration** from **total time to Ready**.
7. Do not sum durations of nested steps when reporting totals.
8. Align JFR timings with startup log timestamps and readiness transitions.
9. Avoid leaving DEBUG logging causing heavy overhead in only one group.
10. Measure side effects too: skipped cache warm-up may speed startup while making first requests slow or failing.
11. Ensure recording files are not truncated on container exit.
12. Do not compare a developer laptop against a CPU-throttled Kubernetes pod and attribute the entire gap to Spring.

**A startup measurement problem should state its target:** "from JVM launch to ApplicationReadyEvent", "refresh time", "time of a custom bean", or "Pod Ready time". Milestones are not interchangeable and can be affected by network/probe scheduling.

### Example A/B Evaluation Table

| Metric | Baseline | After change | How to interpret |
| --- | --- | --- | --- |
| Refresh time | Measured from startup steps | Measured similarly | Did work inside the context decrease? |
| Ready latency | Measured from logs/events | Measured similarly | Did runners alter the outcome? |
| Total CPU in startup | JFR CPU/profile | Same settings | Did CPU work decrease? |
| GC pauses in startup | JFR GC events | Same settings | Were allocation/GC stalls reduced? |
| First-request latency | Additional load test | Same workload | Was cost merely pushed to the first request? |
| Correctness | Integration tests | No regression | Was correctness not traded away for speed? |

Do not invent numbers for the table since they depend on the real application. This table is an **evaluation framework**, not measured data.

## 14. Common Pitfalls When Using FlightRecorderApplicationStartup

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| No Spring startup events visible | Did not call `setApplicationStartup` before `run` | Configure properly in `main` |
| JVM JFR events present but no custom Spring steps | Using `ApplicationStartup.DEFAULT`/no-op | Switch to `FlightRecorderApplicationStartup` |
| Spring steps in code yet `.jfr` file missing | JFR not enabled, no write permission, dump failed | Check `-XX:StartFlightRecording` and JVM output |
| JFR recorded late, missing Environment phase | Used `jcmd` after startup or delay too long | Enable recording at JVM launch |
| `jfr print --events StartupEvent` shows nothing | Wrong event name | Use fully qualified name from `jfr metadata` |
| `demo.catalog.initialize` missing | Custom step not called/ended | Verify bean created and `finally` calls `step.end` |
| Very large `StartupStep` duration yet low CPU | Blocked on I/O/sleep/GC pause | Correlate with JVM events and app metrics |
| Summed durations exceed startup time | Nested/overlapping steps | Use timeline, do not sum raw |
| Boot actuator `/startup` does not show JFR steps | Endpoint requires matching buffering data | Use `BufferingApplicationStartup` or analyze `.jfr` |
| GC events visible yet ClassLoad missing | Different recording settings/thresholds | Check JFR event configuration |
| JFR file overwritten across trials | Reused same filename | Name uniquely per run/PID/timestamp |
| No `jfr` CLI inside container | Minimal runtime image | Copy `.jfr` to a machine with a full JDK |
| Cannot read file after container restart | File written to ephemeral filesystem | Use proper volume/artifact collection |
| Put sensitive data into `StartupStep.tag` | Tags are recorded in the recording | Remove secrets/PII, restrict access |
| Changed application startup strategy twice | Later set overwrites earlier one | Pick one clear strategy |
| Optimized refresh only yet Ready is not faster | Runners/external dependencies still slow | Measure Started-to-Ready time too |
| Used CPU profile to infer all I/O waiting | CPU sampling misses waiting time | Combine socket/thread/park events and custom steps |

### Analysis Mistakes to Avoid

A JFR trace without **jdk.GarbageCollection** is not enough to conclude GC never occurred. The event may be disabled, the threshold may differ, or the recording window missed that moment. Similarly, missing Spring steps can occur because instrumentation was not installed, the event was disabled, or the file was written after the steps finished.

**Always verify recording window, event types, and settings before drawing conclusions.**

## 15. Production Observability: Performance, Security, and Operations

JFR can have low recording overhead with proper settings, yet **it is not completely free**. In production:

- Use **settings=default** or a custom policy for periodic recordings, and **settings=profile** for targeted investigations.
- Cap **maxsize/maxage/duration**; prevent recording files from filling disk unchecked.
- Store recordings only in directories with appropriate permissions.
- Keep secrets and sensitive data out of tags/custom events.
- Enforce a data retention/deletion policy.
- With many replicas, avoid enabling across all at once before measuring resource impact.
- Record metadata: service version, JDK version, image digest, Pod/container ID, and recording time, following security rules.
- Create files only when needed, or use controlled JFR collection infrastructure.
- If production uses minimal JVM images, plan to pull files and analyze in another environment.
- When using JMC, avoid uploading recordings containing production data to unapproved external services.
- Do not use JFR to replace infrastructure metrics, distributed tracing, or health/readiness probes.

**Do not attach a long-running recording just to measure one startup.** When cold startup is the goal, a short recording enabled from JVM launch is usually easier to analyze and lighter on resources.

## 16. Actively Testing the Difference Between JFR and Startup Buffering

### Experiment A — FlightRecorderApplicationStartup

Run the main example with:

~~~bash
java -XX:StartFlightRecording=filename=flight-a.jfr,settings=profile,dumponexit=true \
  -jar target/jfr-startup-demo-0.0.1-SNAPSHOT.jar
~~~

Expected behavior in essence:

- File **flight-a.jfr** exists if the recording dumped successfully.
- Spring startup events are present, including the demo's custom steps.
- JVM events can also be inspected in the same file.
- No HTTP Actuator endpoint is needed.

### Experiment B — Not Setting ApplicationStartup

In a local copy of the project, remove the call:

~~~java
app.setApplicationStartup(
        new FlightRecorderApplicationStartup());
~~~

This is a source code edit **only in an experimental copy**, not a change to make to production code. If the demo code still injects **ApplicationStartup**, Spring can supply the default no-op strategy; custom step methods still run, yet are not exported as JFR events.

Enable JFR as before. JVM events can still be recorded, yet **do not expect Spring's FlightRecorderStartupEvent** merely because JFR is running. This proves **enabling JFR** and **enabling Spring instrumentation** are two separate steps.

### Experiment C — Increasing Simulated Duration

Change the sleep in **demo.catalog.initialize** from 300ms to 700ms, rebuild, and re-run with a different filename. Absent anomalies, the corresponding custom step's duration tends to increase. **Do not demand an exact 400ms delta** due to JVM scheduling, build/run variance, and event overhead.

Compare on the timeline how the catalog increase can lengthen **spring.context.refresh** and the Ready timestamp, without adding the custom step to the parent step as two independent parts.

### Experiment D — Moving Work to a Runner

If a mandatory task is moved from `@Bean` initialization to an `ApplicationRunner` (respecting dependencies and readiness policy):

- **context refresh** may become shorter.
- **time to ApplicationReadyEvent** may not decrease, because the runner still has to do the work.
- JFR lets you verify where the cost shifted.
- If the runner returns early with an asynchronous task, startup can appear "artificially" faster while the app receives traffic before resources are ready.

The goal is not merely optimizing one number, but **reducing true time-to-readiness while preserving correctness**.

## 17. Practice Questions

**Question 1.** Is `FlightRecorderApplicationStartup` in Spring Boot or Spring Framework? What is its full package?

**Question 2.** Why might running the JVM with `-XX:StartFlightRecording` not necessarily produce Spring `StartupStep` events?

**Question 3.** Why should `setApplicationStartup` be called before `SpringApplication.run` instead of declaring it as a `@Bean` in a configuration class?

**Question 4.** What roles do `StartupStep.start`, `tag`, and `end` play? Why must `end` be called in `finally`?

**Question 5.** When seeing `spring.context.refresh` duration 800ms and a child step 300ms, can you add them to get 1100ms?

**Question 6.** When a Spring bean waits 600ms on network, can you conclude the bean consumed 600ms of CPU?

**Question 7.** Can using `jcmd JFR.start` after `ApplicationReadyEvent` reconstruct startup events that occurred earlier?

**Question 8.** Distinguish `FlightRecorderApplicationStartup` and `BufferingApplicationStartup` in terms of where data is stored and analysis tools.

**Question 9.** Why doesn't `/actuator/startup` automatically replace a `.jfr` file?

**Question 10.** Why shouldn't a custom tag contain a password or JDBC URL with credentials?

**Question 11.** If `jfr summary` has no `ClassLoad` events, can you conclude the JVM loaded zero classes during startup?

**Question 12.** An application starts faster after enabling lazy initialization, yet the first request is noticeably slower. Should this be considered a win?

**Question 13.** In the demo program, which custom step is called during refresh and which during the runner?

**Question 14.** What problems can a 10-minute `profile` recording across hundreds of replicas cause?

### Suggested Answers

1. Belongs to Spring Framework; **org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup**.
2. Because an `ApplicationStartup` implementation must be attached to Spring before startup, and the JFR recording must also capture the right event.
3. `@Bean` is created during refresh, too late for the earliest steps.
4. `start` opens the step, `tag` adds context, `end` finishes recording; `finally` guarantees `end` even on exception.
5. No; parent can enclose child.
6. No; duration may be wall-clock waiting.
7. No; a late-started recording does not recover past history.
8. FlightRecorder emits JFR events; Buffering stores steps in memory and can export via Actuator.
9. Actuator's startup endpoint is not the JVM Flight Recorder and does not contain full JVM profiling events.
10. `.jfr` files can be downloaded, shared, and stored; tags can leak sensitive information.
11. No; check event settings, recording window, and version.
12. Not necessarily; measure readiness and end-to-end first-request behavior.
13. **demo.catalog.initialize** in `@Bean`; **demo.runner.validate** in `ApplicationRunner`.
14. File size, overhead, security/retention, and collection operational cost can become excessive.

## 18. Checklist Before Finalizing a Startup Conclusion

- [ ] Verified actual Spring Boot/JDK version rather than using docs for another version?
- [ ] Have **FlightRecorderApplicationStartup** from the right package?
- [ ] Set ApplicationStartup **before run()**?
- [ ] JVM had JFR enabled from launch, **without a delay missing early phases**?
- [ ] File path and filesystem permissions are valid?
- [ ] Have **dumponexit=true** or a duration/dump policy ensuring recording creation?
- [ ] Used **jfr summary** to inspect the recording?
- [ ] Used the exact event name from **jfr metadata** and filtered properly?
- [ ] Saw at least one reliable custom step with **step.end()**?
- [ ] Avoided summing durations of nested steps?
- [ ] Correlated with GC, CPU, I/O, class loading, or thread events?
- [ ] Separated refresh time, runners, and Ready?
- [ ] Measured baseline and multiple runs with consistent configuration?
- [ ] Tested correctness/first-request latency after optimizing?
- [ ] Kept secrets/PII out of tags/recordings?
- [ ] Avoided confusing `BufferingApplicationStartup` `/actuator/startup` with JFR?
- [ ] Have production-appropriate retention, maxsize, and access control?

## 19. Conclusion

**FlightRecorderApplicationStartup** is the bridge to bring **Spring StartupSteps** into **Java Flight Recorder**. It must be configured via **SpringApplication.setApplicationStartup(...)** before **run()** starts. At the same time, the JVM must have **JFR recording enabled from launch** if you want visibility across all startup stages.

Then:

~~~text
Spring startup steps
  (refresh, bean creation, custom steps)
             |
             v
FlightRecorderApplicationStartup
             |
             v
Spring-specific JFR events
             |
             +------------------------+
             |                        |
       JVM GC/CPU/ClassLoad      App custom steps
             |                        |
             +------------+-----------+
                          |
                    startup.jfr
                          |
                 jfr summary/print
                          |
               JDK Mission Control
                          |
               Bottleneck hypothesis
                          |
            Optimize and re-measure A/B
~~~

The most important thing is not "having a JFR file", but **reaching a verifiable conclusion**: a specific startup step is consuming time, the cause lies in Spring/beans, the JVM, or a dependency, and the change improved **real time-to-ready** without sacrificing correctness.

### Official References

1. Spring Boot 3.5 Reference — SpringApplication, Application Startup tracking: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
2. Spring Framework 6.2 JavaDoc — FlightRecorderApplicationStartup: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/jfr/FlightRecorderApplicationStartup.html
3. Spring Framework 6.2 Reference — Application startup steps and instrumentation: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
4. Spring Framework 6.2 Appendix — Spring Application Startup Steps: https://docs.spring.io/spring-framework/reference/6.2/core/appendix/application-startup-steps.html
5. Spring Framework 6.2 JavaDoc — ApplicationStartup and StartupStep: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/metrics/ApplicationStartup.html
6. Oracle Java 21 — java command and -XX:StartFlightRecording: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
7. Oracle Java 21 — jfr command summary, print, metadata: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
8. Oracle Java 21 — jcmd JFR.start/JFR.dump/JFR.stop: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html

**Scope:** the example is a non-web Spring Boot 3.5.x application on Java 17+, using a JDK with JFR and Maven. For Boot 4.x, Framework 7.x, or other JDK/JMC versions, re-verify APIs, event names, event settings, and tools for the exact version before automating `.jfr` analysis.