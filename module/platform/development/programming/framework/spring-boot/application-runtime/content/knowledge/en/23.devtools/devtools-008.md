# DevTools: Development-Time Defaults and Their Impact on Timing Measurements in Spring Boot

## 1. The Problem: Fast on Restart Does Not Mean Fast in Real Deployment

Spring Boot DevTools is designed to shorten the programming feedback loop. It automatically adjusts several properties for development, watches classpath changes, and restarts the application within the same JVM. These conveniences make the local environment **differ from production in caching, classloading, JVM state, logging, and resource lifecycles**.

What matters most when measuring performance:

- **Cold start time**: launching a new JVM/process, loading the framework, and building the application context.
- **DevTools restart time**: the JVM is already running and the base classloader remains; DevTools creates a new restart classloader/context.
- **Time from Save to seeing changes**: includes IDE/build compilation, classpath copying, file watcher delay, context restart, and browser refresh.
- **Time from `ApplicationStartedEvent` to `ApplicationReadyEvent`**: the post-context-refresh startup segment, including `ApplicationRunner`/`CommandLineRunner`.
- **First-request vs. warm-request latency**: depends on template caches, static resource caches, JIT, connection pools, and lazy beans.

**Do not compare measurements with different boundaries as if they were the same metric.** A `Started ... in 0.8s` line after a DevTools restart does not prove an executable JAR on a fresh JVM will also be ready in `0.8s`.

This lesson uses **Spring Boot 3.3.x, Java 17+**, with examples on Boot **3.3.13**. The default property list below applies to Boot **3.3**; newer versions may add or rename certain properties.

## 2. How Is DevTools Added to an Application?

### Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
~~~

Use **`developmentOnly`** (Gradle) or **`optional`** (Maven) so the DevTools dependency does not propagate like a regular dependency. Per Spring Boot, DevTools **is excluded from repackaged executable JARs by default**. When running via **`java -jar`** in normal packaged application mode, DevTools features are disabled.

Therefore, **`bootRun`/IDE with DevTools** and **`java -jar` without DevTools** are not identical even with identical source code. Never add remote DevTools or force-enable DevTools in production, due to security and operational risks.

| Launch Mode | Can DevTools Run? | Purpose |
| --- | --- | --- |
| IDE/Gradle `bootRun` with `developmentOnly` | Yes | Development loop |
| `bootRun` with `spring.devtools.add-properties=false` | Yes, without injecting the defaults group | Isolate impact of development defaults |
| `bootRun` with restart disabled | Other features may still run | Diagnose classloader/restart |
| `bootJar` + `java -jar` (default) | DevTools absent from artifact | Closer-to-production measurement |
| Forcing DevTools into packaged app | Can activate if forced | Never use in production |

## 3. Development Property Defaults in Spring Boot 3.3

Spring Boot 3.3 DevTools automatically adds the following configuration group **when DevTools is active and `spring.devtools.add-properties` is not disabled**:

| Property | Development Value | Meaning |
| --- | --- | --- |
| `server.error.include-binding-errors` | `always` | Binding error details to aid debugging |
| `server.error.include-message` | `always` | Returns error messages when applicable |
| `server.error.include-stacktrace` | `always` | Can expose stack traces in error responses |
| `server.servlet.jsp.init-parameters.development` | `true` | JSP development mode |
| `server.servlet.session.persistent` | `true` | Supports session persistence across dev restarts |
| `spring.docker.compose.readiness.wait` | `only-if-started` | Adjusts waiting for Boot-started Compose services |
| `spring.freemarker.cache` | `false` | Disables FreeMarker template caching |
| `spring.graphql.graphiql.enabled` | `true` | Enables GraphiQL when GraphQL integration is present |
| `spring.groovy.template.cache` | `false` | Disables Groovy template caching |
| `spring.h2.console.enabled` | `true` | Enables H2 console when H2 is present |
| `spring.mustache.servlet.cache` | `false` | Disables Mustache servlet template caching |
| `spring.mvc.log-resolved-exception` | `true` | Logs resolved MVC exceptions |
| `spring.reactor.netty.shutdown-quiet-period` | `0s` | Reduces quiet period on Reactor Netty shutdown |
| `spring.template.provider.cache` | `false` | Disables template provider discovery caching |
| `spring.thymeleaf.cache` | `false` | Disables Thymeleaf compiled template caching |
| `spring.web.resources.cache.period` | `0` | Avoids long cache periods for static resources |
| `spring.web.resources.chain.cache` | `false` | Disables resource chain caching |

**This table does not mean every integration is installed.** `spring.h2.console.enabled=true` does not add the H2 dependency, just as `spring.thymeleaf.cache=false` does not add the Thymeleaf engine. A property takes effect only when the corresponding technology is present and auto-configured.

**Do not copy Spring Boot 4.x defaults into Boot 3.3.** For instance, default error keys in Boot 3.3 use **`server.error.include-...`**; newer versions' docs may have different keys and defaults. If benchmarks inform deployment decisions, record the exact version.

### Why Are Caches Disabled?

In development, developers want to edit HTML/CSS and see changes promptly without template caches hiding them. DevTools prioritizes that experience. In production, caches reduce template parsing overhead, resource lookups, and HTTP transfers.

Consequences:

1. **Thymeleaf/FreeMarker/Mustache:** a view may be resolved/parsed repeatedly, causing differences between first-request and warm-request latency.
2. **Static resources:** cache period `0` and `resource.chain.cache=false` alter headers and lookups, potentially causing browsers to send more requests.
3. **CPU/GC:** allocating more objects while rendering or resolving resources changes CPU and allocation profiles.
4. **p95/p99:** different template processing and browser caching paths make percentiles non-representative of production.
5. **Startup:** the impact does not necessarily show up in `ApplicationReadyEvent`; many templates are parsed only when the first request arrives **after Ready**.

**Do not assume `spring.thymeleaf.cache=false` always slows startup:** if no rendering happens before Ready, caching mainly impacts request latency rather than bean initialization. Measure **startup, first request, and warm requests** separately.

### Other Defaults Also Affect Measurements

- **`server.error.include-stacktrace=always` and `spring.mvc.log-resolved-exception=true`:** error-path responses and logging can be slower and unrepresentative of production; stack traces also carry information-disclosure risk.
- **`spring.reactor.netty.shutdown-quiet-period=0s`:** alters the shutdown wait window, changing total restart-cycle timing for reactive servers.
- **`spring.docker.compose.readiness.wait=only-if-started`:** dependency readiness wait differs when Compose is already running versus freshly started by Boot.
- **`server.servlet.session.persistent=true`:** sessions can survive restarts in supporting setups, altering state between a warm restart and a fresh cold process.
- **`spring.h2.console.enabled` and `spring.graphql.graphiql.enabled`:** expose development surfaces requiring access control; do not include them in production benchmarks if absent in production.

**DevTools does not enable all loggers at DEBUG by default.** Documentation suggests enabling the web DEBUG logging group when inspecting requests. If you add `logging.level.web=DEBUG`, document it because logging I/O affects performance measurements.

## 4. Disabling Development Defaults vs. Disabling Restart

Disable the development defaults group:

~~~properties
spring.devtools.add-properties=false
~~~

This **does not disable DevTools restart**, remove the dependency from the classpath, disable LiveReload, or recreate a cold JVM start.

If you only want Thymeleaf caching enabled as in normal environments, override it:

~~~properties
spring.thymeleaf.cache=true
~~~

Explicitly configured application properties override DevTools defaults. Remaining development defaults—such as static resource period `0` or `stacktrace=always`—stay active.

### Distinguishing Four Flags

| Flag | What It Does | What It Does Not Solve |
| --- | --- | --- |
| `spring.devtools.add-properties=false` | Stops injecting development defaults | Does not disable restart |
| `spring.devtools.restart.enabled=false` in `application.properties` | Stops watching and restarting on classpath changes | Restart classloader may still be initialized |
| `-Dspring.devtools.restart.enabled=false` before `SpringApplication.run` | Disables all restart support per Boot 3.3 guide | Does not inherently remove development defaults |
| `spring.devtools.livereload.enabled=false` | Disables the LiveReload server | Does not disable restart or defaults |

Per Boot 3.3 documentation, **setting `restart.enabled=false` in `application.properties` alone does not completely eliminate the restart classloader**. To turn it off completely, set the **JVM System property** before `SpringApplication.run` or omit the DevTools dependency from the classpath.

For genuine production benchmarks, the most reliable method is **using a build without DevTools** and controlling the JVM launch; never assume a single flag makes everything identical to production.

## 5. DevTools Restart and Two Classloaders

~~~text
Living JVM process
       |
       +-- Base classloader
       |     Rarely changing libraries/JARs
       |
       +-- Restart classloader #1
       |     Application classes
       |     ApplicationContext #1
       |
IDE build/copy changes classpath
       |
       +-- Close context #1
       +-- Discard restart classloader #1
       +-- Create restart classloader #2
       +-- Create ApplicationContext #2
       |
       +-- Base classloader and JVM remain alive
~~~

In a **cold start**, the JVM, classloading, runtime caches/JIT, and context all start from a fresh process state. In a **DevTools restart**, the JVM and base classloader already exist, so restarts are usually faster than cold starts.

Do not equate restart with JVM process exit/relaunch, nor think restart patches bytecode in-place for every class. External library classes normally remain in the base classloader, while classes under development go into the restart classloader.

### A Single Save Involves Multiple Time Spans

~~~text
Save source
  -> IDE/Gradle compile, copy classpath
  -> FileSystemWatcher poll/quiet period
  -> DevTools detects change
  -> Old context shuts down
  -> New restart classloader/context
  -> ApplicationStartedEvent
  -> Runners
  -> ApplicationReadyEvent
  -> Browser LiveReload
~~~

The span **from Save to updated browser content** includes IDE build time, the watcher, and the browser. **`ApplicationReadyEvent.getTimeTaken()` does not measure anything before `SpringApplication` starts**.

DevTools watches **classpath output changes**, rather than simply reading `.java` files the moment you press Save. In IntelliJ, `Build Project`/output copying may be required; IDE auto-compile adds its own delay.

Directories such as `templates`, `static`, `public`, and `META-INF/resources` do not trigger a **full context restart** by default, though they can trigger LiveReload. Editing CSS and seeing the browser refresh is not proof startup just re-ran.

### File Watcher Timing

Configurable via:

~~~properties
spring.devtools.restart.poll-interval=2s
spring.devtools.restart.quiet-period=1s
~~~

These values govern change detection cadence and file stability waiting. They are **not** Spring bean creation time or `ApplicationContext.refresh` time. When measuring developer feedback, include watcher delay; when measuring runtime startup, exclude watcher delay from the metric.

## 6. Clocks Must Use the Right Boundaries

| Metric | Scope |
| --- | --- |
| `ApplicationStartedEvent.getTimeTaken()` | Spring Boot to started, after context refresh, before runners |
| `ApplicationReadyEvent.getTimeTaken()` | Spring Boot to ready, after runners |
| `application.started.time` | Micrometer metric for total time to started |
| `application.ready.time` | Micrometer metric for total time to ready |
| `RuntimeMXBean.getUptime()` | JVM process uptime; keeps increasing across DevTools restarts |
| save-to-reload elapsed | IDE compile + watcher + old shutdown + new startup + browser |
| first HTTP response | Network + routing + lazy init + template parse/cache + response |
| warm HTTP requests | Steady-state latency, dependent on JIT/caches and workload |

Both events expose `getTimeTaken()` returning a **`Duration`**, which can be `null` if unknown. Practical code handles `null` rather than arbitrarily substituting `0`.

**Logical example:** after 10 source edits, the JVM process has been up for 30 minutes, yet Ready duration for one DevTools restart is a few hundred milliseconds. Both numbers are valid because they measure different intervals. Never subtract from process uptime starting at 0 and call it startup duration.

Never wrap a long-lived web server with a shell `time` command until shutdown to infer startup time. If the process serves requests for 10 minutes, wall time includes those 10 minutes of serving, not just Spring initialization.


## 7. Runnable Spring Boot 3.3 / Java 17 Project: Observing Properties and Real Timings

This example uses Gradle, embedded Tomcat, Thymeleaf, and Actuator. It:

- Places DevTools in `developmentOnly`, keeping it out of the default executable JAR.
- Inspects raw `Environment` values and the final **`ThymeleafProperties.isCache()`**.
- Prints `Started` and `Ready` events with durations in ms, handling `null`.
- Prints JVM uptime to distinguish an existing JVM from a context restart.
- Includes a template and static resource to test first/warm requests.
- Allows disabling restart support via a `System` property set before `SpringApplication.run`.

### 7.1. Project Structure

~~~text
devtools-timing-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          DevtoolsTimingDemo.java
      resources/
        application.properties
        templates/
          home.html
        static/
          demo.txt
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'devtools-timing-demo'
~~~

**build.gradle**:

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

Requires JDK 17+, a compatible Gradle installation, and access to download plugins/dependencies or have them cached.

**src/main/resources/application.properties**:

~~~properties
spring.application.name=devtools-timing-demo
server.port=8080
spring.main.banner-mode=off
management.endpoints.web.exposure.include=health,metrics
~~~

We intentionally **omit** `spring.thymeleaf.cache`, `spring.web.resources.cache.period`, and `server.error.include-stacktrace`; if they appear in `Environment` during `bootRun`, they came from DevTools development defaults.

### 7.2. Java Source

File **`src/main/java/demo/DevtoolsTimingDemo.java`**:

~~~java
package demo;

import java.lang.management.ManagementFactory;
import java.time.Duration;
import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.thymeleaf.ThymeleafProperties;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@SpringBootApplication
public class DevtoolsTimingDemo {

    public static void main(String[] args) {
        if (Arrays.asList(args).contains("--demo.disable-restart")) {
            System.setProperty("spring.devtools.restart.enabled", "false");
        }
        SpringApplication.run(DevtoolsTimingDemo.class, args);
    }

    @Bean
    ApplicationRunner reportProperties(
            Environment environment, ThymeleafProperties thymeleaf) {
        return args -> {
            System.out.println("RUNNER_BEGIN");
            System.out.println("ENV_THYMELEAF_CACHE="
                    + environment.getProperty(
                            "spring.thymeleaf.cache", "<unset>"));
            System.out.println("EFFECTIVE_THYMELEAF_CACHE="
                    + thymeleaf.isCache());
            System.out.println("ENV_STATIC_CACHE_PERIOD="
                    + environment.getProperty(
                            "spring.web.resources.cache.period",
                            "<unset>"));
            System.out.println("ENV_ERROR_STACKTRACE="
                    + environment.getProperty(
                            "server.error.include-stacktrace",
                            "<unset>"));
            System.out.println("RUNNER_END");
        };
    }
}

@Component
class StartupTimingEvents {

    @EventListener
    public void started(ApplicationStartedEvent event) {
        System.out.println("EVENT_STARTED");
        printDuration("STARTED_MS", event.getTimeTaken());
    }

    @EventListener
    public void ready(ApplicationReadyEvent event) {
        System.out.println("EVENT_READY");
        printDuration("READY_MS", event.getTimeTaken());
        System.out.println("JVM_UPTIME_MS="
                + ManagementFactory.getRuntimeMXBean().getUptime());
    }

    private static void printDuration(String key, Duration value) {
        if (value == null) {
            System.out.println(key + "=unknown");
        } else {
            System.out.println(key + "=" + value.toMillis());
        }
    }
}

@Controller
class HomePageController {
    @GetMapping("/")
    public String home(Model model) {
        model.addAttribute("title", "DevTools Timing Demo");
        return "home";
    }
}
~~~

**Runnable syntax notes:**

- Only `DevtoolsTimingDemo` is a public class; filename matches. The other two classes are package-private in package `demo`.
- Spring Boot 3.3 provides `getTimeTaken()` on Started/Ready events; `null` is handled safely.
- With the Thymeleaf starter present, Boot auto-configures `ThymeleafProperties`; `isCache()` reflects the effective final value.
- `@Bean ApplicationRunner` runs **after** `ApplicationStartedEvent` and **before** `ApplicationReadyEvent`.
- The System property disabling restart is set **before `run`** when `--demo.disable-restart` is passed.
- `READY_MS` and `JVM_UPTIME_MS` vary every run—never assert fixed numbers.

**src/main/resources/templates/home.html**:

~~~html
<!doctype html>
<html xmlns:th="http://www.thymeleaf.org">
<head><meta charset="UTF-8"><title>Demo</title></head>
<body>
    <h1 th:text="'DevTools Timing Demo'">Fallback</h1>
</body>
</html>
~~~

**src/main/resources/static/demo.txt**:

~~~text
DevTools static resource
~~~

Because the template uses a Thymeleaf attribute, rendering actually passes through the template engine. The same template can test `cache=true/false`, though latency must be measured in practice rather than inferred from HTML content.

## 8. Five Run Modes to Isolate Effects

### Mode A: bootRun with DevTools Defaults

Run if you have the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

If you have no wrapper but have a compatible Gradle installed:

~~~bash
gradle bootRun
~~~

With Spring Boot 3.3.13, DevTools `developmentOnly` active, and no config overrides, lines printed by our code appear in this relative order:

~~~text
EVENT_STARTED
RUNNER_BEGIN
ENV_THYMELEAF_CACHE=false
EFFECTIVE_THYMELEAF_CACHE=false
ENV_STATIC_CACHE_PERIOD=0
ENV_ERROR_STACKTRACE=always
RUNNER_END
EVENT_READY
~~~

Boot/Gradle logs and **`STARTED_MS=...`**, **`READY_MS=...`**, **`JVM_UPTIME_MS=...`** lines interleave with machine-dependent values. Never assert the console prints only the lines above.

### Mode B: Disable Defaults While Keeping Restart

~~~bash
./gradlew bootRun --args="--spring.devtools.add-properties=false"
~~~

Because the project does not declare those raw properties in `application.properties`, expected values are:

~~~text
ENV_THYMELEAF_CACHE=<unset>
EFFECTIVE_THYMELEAF_CACHE=true
ENV_STATIC_CACHE_PERIOD=<unset>
ENV_ERROR_STACKTRACE=<unset>
~~~

**Raw `Environment` differs from binder defaults.** The standard default for `ThymeleafProperties.cache` in Boot 3.3 is `true`, so even when `Environment` returns `<unset>`, the effective value is `true`. Never infer that an absent property automatically defaults to `false`.

DevTools can still auto-restart on classpath changes; this flag **only disables the development defaults group**.

### Mode C: Completely Disable Restart Support and Disable Defaults

~~~bash
./gradlew bootRun --args="--demo.disable-restart --spring.devtools.add-properties=false"
~~~

`main` sets the System property `restart=false` **before `SpringApplication.run`**; this is the Boot 3.3 documented way to disable the restart classloader completely. Simultaneously `add-properties=false` prevents defaults from being added. Even so, the DevTools dependency remains on the development classpath; this is **not** a runtime identical to packaged production.

### Mode D: Executable JAR Without DevTools

~~~bash
./gradlew bootJar
java -jar build/libs/devtools-timing-demo-1.0.0.jar
~~~

Per `developmentOnly` and default packaging, DevTools is absent from the repackaged JAR. Raw/effective Thymeleaf values may resemble B/C, yet this is a **different JVM process/launcher/classpath path** than `bootRun`. Do not attribute the entire timing gap between A and D to DevTools.

### Mode E: Override Only Thymeleaf Cache

~~~bash
./gradlew bootRun --args="--spring.thymeleaf.cache=true"
~~~

Expected property lines:

~~~text
ENV_THYMELEAF_CACHE=true
EFFECTIVE_THYMELEAF_CACHE=true
~~~

Other DevTools defaults remain in effect. This isolates the specific effect of Thymeleaf template caching without disabling the entire development defaults group.

## 9. Measuring Startup vs. First Request vs. Warm Requests

Start the process, wait for Ready, then run:

~~~bash
curl -s http://localhost:8080/
curl -i http://localhost:8080/demo.txt
curl -s http://localhost:8080/actuator/metrics/application.ready.time
~~~

The final Actuator endpoint is accessible only when Actuator is added and metrics are exposed, as in this project. `application.ready.time` is an aggregate meter, not a per-bean profiler.

You can measure client HTTP latency with `curl`:

~~~bash
curl -s -o /dev/null -w "total=%{time_total}s\n" http://localhost:8080/
~~~

Repeat against the same process, content, and cache state, reporting median/p95 across multiple samples. `curl` total time includes HTTP/network overhead; it is not purely Thymeleaf rendering time.

**Separate three measurements:**

1. **Ready duration:** from the Spring Boot event/meter.
2. **First GET after Ready:** can pay costs for lazy beans, template parsing, JSP/engine init, and connection warmup.
3. **Warm GET:** reflects active caching/JIT; production usually uses different caching policies than DevTools.

With `spring.thymeleaf.cache=false`, repeated requests may re-parse templates repeatedly. With `true`, warm requests benefit from caching. Never claim a fixed millisecond difference without running real measurements.

## 10. Flawed Measurement Practices and How to Fix Them

### Flawed: Treating a Warm Restart as a Cold Start

~~~text
DevTools warm restart: 0.9 s
Fresh JVM java -jar: 3.1 s
~~~

These are **hypothetical numbers illustrating flawed reasoning**, not an actual benchmark. That difference cannot prove production is "over three times slower" because multiple variables changed simultaneously.

**Fix:** Every cold-start sample must launch a **fresh JVM/process** with identical JDK, profile, resources, dependency readiness, and launch mode. Record warm restarts separately if measuring the developer loop.

### Flawed: Using JVM Uptime as Ready Duration

A JVM can stay up for hours across dozens of DevTools restarts. Uptime does not reset with `ApplicationContext`. Use `Started`/`Ready` event `Duration` for **each startup**, and uptime to tell whether the process is warm.

### Flawed: Using Save-to-Browser-CSS-Reload Time as Startup Time

Save-to-reload includes IDE compilation, file watcher poll/quiet periods, LiveReload, and network/browser work. Many static/template edits do not even trigger a full context restart. Check whether a new `ApplicationStartedEvent`/`ReadyEvent` occurred, and measure each segment separately.

### Flawed: Enabling DEBUG Logs and Comparing Against Production INFO

Log output, condition evaluation deltas, and IDE console I/O add overhead. Comparisons must use identical logging policies or explicitly state they measure end-to-end developer experience rather than pure startup.

### Flawed: Measuring with Shell `time` on a Long-Lived Web App

A web app running for 10 minutes before being stopped yields wall time including 10 minutes of serving. Never call that startup duration. Use `ApplicationReadyEvent.getTimeTaken()` or readiness polling with clear markers under cold-start conditions.


## 11. Controlled Measurement Matrix

| Run | Launch | Dev Defaults | Restart Classloader | Goal |
| --- | --- | --- | --- | --- |
| A | `bootRun` | Enabled | Enabled | Current development experience |
| B | `bootRun`, `add-properties=false` | Disabled | Enabled | Impact of entire development defaults group |
| C | `bootRun`, early disable-restart + `add-properties=false` | Disabled | Disabled | Remove restart support overhead in dev runtime |
| D | `bootJar` then fresh `java -jar` | No DevTools | Disabled | Cold startup close to production |
| E | `bootRun` + `Thymeleaf cache=true` | Only template cache overridden | Enabled | Caching impact of a single engine |

**Comparing A–B** shows the difference when the defaults group changes, without isolating which individual property caused it. **A–E** is better suited to test Thymeleaf caching. **B–C** reveals what restart support affects on the development classpath. **C–D** changes both launcher and classpath, so it is not a single-variable comparison.

Record for every run:

| Field | Why Record It? |
| --- | --- |
| JDK, Boot, Gradle, OS | Classloading/GC/runtime differ |
| App version, commit, profile | Identical code and feature flags |
| Fresh vs. reused JVM | Cold vs. warm restart |
| DevTools classpath, defaults, restart flags | Core variables of this lesson |
| Effective template/static cache values | Proves actual configuration |
| CPU quota, heap, GC | Resources affect every duration |
| DB/broker readiness and external I/O | Startup can block on dependencies |
| Started/Ready ms | `SpringApplication` milestones |
| JVM uptime ms | Detects already-warm processes |
| First HTTP and warm p95 | Reflects caching/lazy/rendering |
| Watcher/compile delay | Only for developer feedback loop measurements |

Run multiple independent samples per configuration with proper warmup when measuring HTTP, reporting medians/distributions instead of cherry-picking best runs. **Never fabricate benchmark numbers**: example figures do not replace measurements from your own machine.

## 12. When Deeper Bean-Level Profiling Is Needed

You can instrument startup with `BufferingApplicationStartup`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setApplicationStartup(new BufferingApplicationStartup(2048));
app.run(args);
~~~

**This is an illustrative snippet**: it requires importing `BufferingApplicationStartup` and a real `MyApplication` class. `setApplicationStartup` must be called before `run` to capture early Spring startup steps.

With Actuator and the `startup` endpoint exposed, **`GET /actuator/startup`** returns a snapshot and **`POST /actuator/startup`** retrieves and drains the buffer. The timeline helps pinpoint slow bean instantiation or context phases; still, never treat a warm DevTools restart timeline as equivalent to a cold JVM. Do not sum nested step durations to compute total startup, as that double-counts overlapping scopes.

To inspect JVM classloading, allocations, JIT, and GC alongside Spring startup, use **Java Flight Recorder (JFR)**. For aggregate timings across deployments, use **`application.started.time` and `application.ready.time`** from Micrometer/Actuator.

**`READY_TIME - STARTED_TIME`** can reflect the span between those two milestones in the same startup, usually covering runners, yet it is not pure runner CPU time and should not be computed if either `Duration` is `null`.

## 13. Other DevTools Factors That Can Skew Measurements

### Condition Evaluation Delta Logs

Each DevTools restart can print a condition evaluation delta report. To disable this log:

~~~properties
spring.devtools.restart.log-condition-evaluation-delta=false
~~~

This only stops logging the delta; **it does not disable restart**. Large log volumes on an IDE console add I/O and CPU overhead, especially when timing the end-to-end developer cycle.

### LiveReload

~~~properties
spring.devtools.livereload.enabled=false
~~~

Disables only the LiveReload server; does not remove the restart classloader or development property defaults. Never treat automatic browser refreshes as proof the context restarted. If multiple DevTools apps run concurrently, only one LiveReload server can bind the default port.

### Global DevTools Settings

DevTools can read `spring-boot-devtools.properties`, `.yaml`, or `.yml` from **`HOME/.config/spring-boot`** or legacy fallback locations. Two machines with identical source code but different global settings can behave differently. Check global configs and `SPRING_DEVTOOLS_HOME` or `spring.devtools.home` when investigating.

### Old Context Shutdown Duration

DevTools restart relies on the Spring context's shutdown hook. If code disables shutdown hook registration, Boot 3.3 docs warn restart may malfunction. The cost of HTTP draining, `SmartLifecycle.stop`, executor cleanup, and closing database pools belongs to the **old shutdown phase**, not the new `SpringApplication`'s `Duration`. When measuring the full Save-to-Ready cycle, account for both phases.

### Classloader Leaks Across Restarts

Some libraries keep static references, `ThreadLocal`s, background threads, or deserialization caches pointing to classes from an old restart classloader. This can cause memory leaks or classloading errors visible only across repeated restarts. When this happens, test disabling restart early, inspect **`META-INF/spring-devtools.properties`** rules, and fix cleanup; never rely on a single warm restart to conclude production heap usage is stable.

## 14. Quick Symptom-Based Diagnosis

| Symptom | Likely Explanation | Action |
| --- | --- | --- |
| `bootRun` has `cache=false` yet JAR has `cache=true` | DevTools defaults disable caches in dev | Inspect `Environment` and `ThymeleafProperties` |
| `spring.devtools.add-properties=false` yet app still restarts | Flag only disables defaults | Check `restart.enabled` |
| `restart.enabled=false` in properties yet restart classloader exists | Per docs, classloader may still initialize | Set `System` property before `run` |
| Very small `Started in X` after editing a file | JVM and base classloader are already warm | Compare against a fresh cold process |
| Large JVM uptime with small Ready duration | Warm restart inside the same JVM | Distinguish process runtime from context duration |
| Editing template emits no new `Started` event | Template only triggered LiveReload, not full restart | Check resource exclusions |
| Saving waits several seconds before starting restart | IDE compile + watcher poll/quiet period | Measure prior to `SpringApplication` |
| Template requests are slow in dev | `Thymeleaf cache=false`, JIT/cold state | Test `cache=true` in the same launch mode |
| Error response leaks stack trace | DevTools `server.error.include-stacktrace=always` | Never expose dev configs in production |
| WebFlux shutdown differs | Dev Reactor Netty quiet period is `0s` | Separate shutdown timing |
| RAM grows across restarts | Possible classloader/reference/resource leak | Capture heap dump, disable restart to compare |
| Metrics endpoint returns 404 | Missing Actuator/exposure or security rules | Check dependencies and management config |

## 15. Common Misconceptions

**"Adding DevTools makes production faster."** False: DevTools is a development tool; production artifacts must not include it.

**"DevTools always makes every app start slower."** No absolute rule: defaults, classloaders, caches, and workloads can make different milestones faster or slower.

**"DevTools automatically turns on all DEBUG logs."** False: docs merely suggest web DEBUG; check actual log levels.

**"Disabling development property defaults disables restart."** False: `add-properties` and restart are independent.

**"Disabling restart in `application.properties` completely removes the classloader."** Not per Boot 3.3 docs; to disable completely, set the `System` property before `run`.

**"After a DevTools restart, there is a new JVM."** False: the base classloader/JVM is reused.

**"A `Started in 0.7 s` line is Save-to-browser time."** False: IDE compilation, watcher, and LiveReload lie outside that milestone.

**"`JVM_UPTIME_MS` equals `READY_MS`."** False: process uptime does not reset across restarts.

**"The first request represents steady-state."** No: caches, JIT, lazy init, and connection warmup skew it.

**"Template caching disabled in dev does not affect benchmarks."** It can heavily impact view rendering paths; test under controlled settings.

**"Static resource changes always restart the app."** False: many resources are excluded from restart triggers.

**"DevTools defaulting GraphiQL/H2 means every app already has H2/GraphQL."** False: the corresponding integrations are still required.

**"Enabling error stack traces is always safe because it's just logs."** False: it can appear in HTTP error responses and must not be exposed publicly.

**"Measuring startup via wall time of a web server living 20 minutes."** False: that is process lifetime, not time to Ready.

## 16. Self-Check Questions

**Question 1.** What does DevTools 3.3 set `spring.thymeleaf.cache` to?  
**Answer:** `false` when development defaults are active.

**Question 2.** What is `ThymeleafProperties.cache`'s normal default without overrides?  
**Answer:** `true` in Boot 3.3.

**Question 3.** Does `spring.devtools.add-properties=false` disable restart?  
**Answer:** No, it only disables the defaults group.

**Question 4.** Does a DevTools restart create a new JVM process?  
**Answer:** Normally no; the JVM/base classloader is retained.

**Question 5.** What must you do to disable the restart classloader completely?  
**Answer:** Set System property `restart.enabled=false` before `SpringApplication.run`, or omit the DevTools dependency.

**Question 6.** Is a small Ready time alongside a one-hour process uptime contradictory?  
**Answer:** No. One measures context startup duration; the other measures JVM age.

**Question 7.** Does `ApplicationReadyEvent.getTimeTaken` include IDE compilation?  
**Answer:** No.

**Question 8.** Why should you not compare a `cache=false` first request against a `cache=true` warm request?  
**Answer:** Workload, caching, JIT, and lazy state all differ.

**Question 9.** Does LiveReload imply a context restart?  
**Answer:** No.

**Question 10.** When does DevTools' error-stacktrace default pose a risk?  
**Answer:** When error responses expose stack traces, especially if dev config leaks into a public environment.

**Question 11.** What should you use to find which bean starts up slowly?  
**Answer:** `ApplicationStartup`/`BufferingApplicationStartup`, combined with metrics or JFR.

**Question 12.** How must you measure cold starts fairly?  
**Answer:** Spawn a new JVM per run with identical JDK, launcher, profiles, resources, and downstream conditions.

**Question 13.** What is wrong with changing a Spring Boot property without recording it in the benchmark report?  
**Answer:** Results become irreproducible and root causes cannot be attributed accurately.

**Question 14.** What must developer Save-to-Ready measurements include beyond `SpringApplication`?  
**Answer:** IDE compilation, watcher delay, old context shutdown, and browser reload when applicable.

## 17. Checklist Before Drawing Performance Conclusions

- [ ] Recorded exact Boot 3.3.x, JDK, launcher, and build/profile.
- [ ] Confirmed DevTools is strictly in `developmentOnly` or Maven `optional`.
- [ ] Checked whether DevTools-injected default properties are actually active.
- [ ] Separated `add-properties`, `restart.enabled`, and `livereload.enabled`.
- [ ] Checked **effective configuration**, not just raw `Environment` keys.
- [ ] Measured `StartedEvent`/`ReadyEvent` `Duration`, handling nullability.
- [ ] Used JVM uptime only to detect warm processes, never calling it startup time.
- [ ] Did not compare warm DevTools restarts with cold production JVMs as equivalent.
- [ ] Measured first/warm requests separately with explicit template/static cache policies.
- [ ] Controlled for JIT, GC, CPU/RAM, connection pools, and dependency readiness.
- [ ] Distinguished build/IDE watcher time from `SpringApplication` execution time.
- [ ] Repeated experiments, reported medians/percentiles, and stored metadata.
- [ ] Used `ApplicationStartup`, Actuator metrics, or JFR when deeper explanation was needed.
- [ ] Never enabled remote DevTools or debug/stacktrace info in production.

**Conclusion:** DevTools alters **property defaults for developer convenience**, splits **base/restart classloaders** for fast restarts, and includes **LiveReload** for browsers. These changes affect caching, logs, lifecycles, classloading, and how timings are defined. In Spring Boot 3.3, **`spring.devtools.add-properties=false`** disables only development defaults; disabling the restart classloader completely requires setting a System property before `run` or removing the DevTools module. Accurate benchmarking requires comparing identical boundaries for **`Started`/`Ready`, cold/warm processes, cache state, and launch mode**—never extrapolate production cold startups from a single fast DevTools restart.

### References

- [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Startup Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
