# Using @Timed and @Counted with the Appropriate Aspect Mechanism

## 1. Annotations Describe What to Measure; Aspects Perform the Measurement

A method annotated with `@Timed` does not automatically produce a timer. Similarly, adding `@Counted` to source code is not enough for invocation counts to appear automatically in Actuator.

Micrometer's two annotations are **runtime metadata**. There must be a component that understands them and intercepts method calls to start/stop a timing measurement or increment a counter. For regular Spring services, the approach in this lesson uses:

- `TimedAspect` to handle `io.micrometer.core.annotation.Timed`.
- `CountedAspect` to handle `io.micrometer.core.annotation.Counted`.
- Spring AOP to create a stand-in object, called a **proxy**, in front of the measured bean.
- `MeterRegistry` to receive measurements; Spring Boot Actuator enables inspecting or exporting metrics per configuration.

The call flow looks like:

```text
Calling bean
   -> proxy of measured bean
       -> aspect starts observation
           -> business method
       -> aspect ends observation and records to MeterRegistry
   -> returns result or rethrows exception
```

**The critical condition is that the call must pass through a proxy with the corresponding aspect attached.** Calling the target object directly leaves the annotations present, yet no component executes the measurement for that call.

Aspect bean configurations are documented by Micrometer under [@Timed](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation) and [@Counted](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html#_the_counted_annotation). This lesson focuses on custom services in Spring Boot 3.3 and verification examples using Micrometer 1.13.0 and Spring Framework 6.1.8.

## 2. Choose @Timed or @Counted Based on the Question to Answer

| Need | Tool | Primary data |
| --- | --- | --- |
| How long does one execution take? | `@Timed` with a standard timer | Completed count, total duration; additional statistics depending on registry/config |
| How many times does a method complete? | `@Counted` | Counter by execution outcome |
| Count only calls ending with an exception | `@Counted(recordFailuresOnly = true)` | Failure counter |
| How many long tasks are currently running and for how long? | `@Timed(longTask = true)` | `LongTaskTimer`, with semantics different from a standard completion timer |

A standard timer already includes `count`. If the same business boundary is already measured by a timer, do not add a counter solely to recount those exact same events. A separate counter only adds value when it answers a different question, such as processing rejections, or provides genuinely needed classification.

In the experiment below, both a timer and a counter are placed on an asynchronous method simultaneously to compare the **recording timing** of the two aspects. That is deliberate for the experiment; in real applications, pick the instrument that suffices to answer your question.

### Names, Descriptions, and Fixed Tags

Example declaration on an existing method:

```java
@Timed(
    value = "app.invoice.generate",
    description = "Time spent generating an invoice",
    extraTags = {"format", "pdf"}
)
```

Or:

```java
@Counted(
    value = "app.invoice.rejected",
    recordFailuresOnly = true,
    extraTags = {"channel", "batch"}
)
```

`extraTags` consists of key/value pairs, so the number of elements must be even. Names should be stable and describe one activity; tags describe classification dimensions with finite value sets. Never use invoice IDs, emails, exception messages, or arbitrary parameter values as tags.

With the default aspects in the example, the timer includes tags such as `class`, `method`, and `exception`; the counter also adds `result`. Avoid defining custom tags with the same names but different meanings. Annotations do not create dashboards or alerts automatically.

## 3. Proper Configuration in Spring Boot 3.3

### 3.1. Having the AOP Library and Having Aspect Beans Are Two Separate Requirements

In a Spring Boot project with dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Actuator provides the metrics infrastructure and registry suited to the application. The AOP starter provides the dependencies for the proxy/aspect mechanism. For custom services to be intercepted explicitly, register the two aspects using **the Spring-managed MeterRegistry**:

File `MethodMetricsConfiguration.java`, within component/configuration scan scope:

```java
package demo;

import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MethodMetricsConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }
}
```

Register each aspect type only once in the active configuration. If your application or an internal library already provides the aspect, use that configuration instead of adding a second copy.

Do not use `new SimpleMeterRegistry()` in the configuration above just to make the constructor compile. That private registry is not automatically the registry read by Actuator or a Prometheus exporter. In real applications, inject the `MeterRegistry` bean.

### 3.2. Are @EnableAspectJAutoProxy or a javaagent Required?

Spring Boot 3.3 auto-configures AOP when classpath/configuration conditions match. By default Boot uses class-based proxies; `spring.aop.proxy-target-class=false` switches to interface-based proxies. When auto-configuration is active, there is no need to add `@EnableAspectJAutoProxy` just to repeat what Boot already does. See [Spring Boot 3.3 Aspect-Oriented Programming](https://docs.spring.io/spring-boot/3.3/reference/features/aop.html).

In the **plain Spring** example without Spring Boot, we declare `@EnableAspectJAutoProxy` explicitly.

Spring AOP understands aspects written using AspectJ annotations. That does not mean the example rewrites bytecode via AspectJ weaving. The proxy approach here does not require enabling `-javaagent:aspectjweaver`. Compile-time weaving and load-time weaving are different mechanisms with different configuration and implications; do not mix them into an application merely to get annotations working.

## 4. Proxy Boundaries Determine Which Calls Are Recorded

### 4.1. Calls from Another Bean via an Injected Reference

When bean A receives bean B from Spring and invokes B's measured method, the reference to B can be a proxy. The aspect has the opportunity to intercept that call:

```text
A -> proxy B -> aspect -> B.work()
```

This is the appropriate boundary for measuring a service operation. Keep classes and methods eligible for proxying; for example, regular Java classes with `public`, non-`final` methods.

### 4.2. Self-Invocation Within the Same Object Bypasses the Called Method's Aspect

Suppose the same service has:

```java
public void outer() {
    inner();
}

@Timed("app.inner")
public void inner() {
    // Internal processing.
}
```

This snippet illustrates call boundaries, not a standalone runnable class. When `outer()` executes on the target object, `inner()` is a call through `this`. It does not pass through the proxy again. Therefore, `inner()`'s aspect is not applied solely because of the annotation.

If you need to measure `inner` as an independent operation, extract it into a collaborating bean and call it via an injected bean reference. If you actually only need to measure all of `outer`, place the annotation on `outer`. If you need to measure a small internal block, using `Timer` directly at that boundary can also be clearer than restructuring classes solely to go through a proxy.

### 4.3. Cases to Distinguish

| Call/declaration style | Effect under Spring AOP |
| --- | --- |
| Calling an injected bean from outside | Can be intercepted by the aspect when configuration and method qualify |
| `this.inner()` or `inner()` in the same object | Bypasses advice for the inner call |
| `new SomeService(...).work()` | Directly instantiated object is not a Spring-managed proxy |
| `private` or `static` method | Not an eligible interception point for standard proxy mechanisms |
| `final` class/method with class-based proxy | Cannot subclass/override as needed to apply advice |
| JDK proxy | Calls route through the proxied interface; verify how annotations on implementing methods are resolved |
| Calling inside constructor or bean initialization phase | Do not rely on the proxy already being ready to measure that call |

Do not conclude that every `final` method is impossible under every proxy kind: JDK proxies represent interfaces and behave differently from subclassing proxies. For tests and typical services, the easiest-to-verify choice is a public non-final method on a non-final class. Proxy mechanics and self-invocation are explained in [the Spring AOP documentation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

## 5. Java Experiment: Proving the Conditions with Data

The following program runs plain Spring to make aspect registration and proxy creation transparent. No HTTP server or external monitoring system is needed. It uses `MockClock` to verify durations without `Thread.sleep`.

### 5.1. Separate Gradle Project

Use JDK 17 or later; JDK 21 works too. Create a separate experiment project with `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.8'
    implementation 'org.springframework:spring-aop:6.1.8'
    implementation 'org.aspectj:aspectjweaver:1.9.22'
    implementation 'io.micrometer:micrometer-core:1.13.0'
}

application {
    mainClass = 'demo.MetricsAspectDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
    options.compilerArgs += ['-parameters']
}

tasks.register('copyRuntimeDependencies', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('runtime-libs')
}
```

`settings.gradle`:

```groovy
rootProject.name = 'metrics-aspect-demo'
```

In a real Boot application, let Boot manage dependency versions. The explicit versions here serve only the verified plain-Spring project.

### 5.2. Complete Program

File `src/main/java/demo/MetricsAspectDemo.java`:

```java
package demo;

import io.micrometer.core.annotation.Counted;
import io.micrometer.core.annotation.Timed;
import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class MetricsAspectDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class Config {
        @Bean
        MockClock clock() {
            return new MockClock();
        }

        @Bean
        SimpleMeterRegistry meterRegistry(MockClock clock) {
            return new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        }

        @Bean
        TimedAspect timedAspect(MeterRegistry registry) {
            return new TimedAspect(registry);
        }

        @Bean
        CountedAspect countedAspect(MeterRegistry registry) {
            return new CountedAspect(registry);
        }

        @Bean
        WorkService workService(MockClock clock) {
            return new WorkService(clock);
        }
    }

    public static class WorkService {
        private final MockClock clock;

        public WorkService(MockClock clock) {
            this.clock = clock;
        }

        @Timed(value = "demo.work", extraTags = {"channel", "local"})
        public void work(boolean fail) {
            clock.add(Duration.ofMillis(fail ? 5 : 10));
            if (fail) {
                throw new IllegalArgumentException("Invalid work");
            }
        }

        public void selfInvoke() {
            work(false);
        }

        @Counted(value = "demo.events", extraTags = {"channel", "local"})
        public void event(boolean fail) {
            if (fail) {
                throw new IllegalArgumentException("Invalid event");
            }
        }

        @Counted(value = "demo.failures", recordFailuresOnly = true)
        public void failuresOnly(boolean fail) {
            if (fail) {
                throw new IllegalStateException("Failed operation");
            }
        }

        @Timed("demo.async")
        @Counted("demo.async.completed")
        public CompletableFuture<String> await(CompletableFuture<String> source) {
            return source;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            SimpleMeterRegistry registry = context.getBean(SimpleMeterRegistry.class);
            MockClock clock = context.getBean(MockClock.class);
            WorkService service = context.getBean(WorkService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            service.work(false);
            try {
                service.work(true);
            } catch (IllegalArgumentException expected) {
                // Caller still receives the business exception.
            }
            printTimer(registry, "demo.work", "none");
            printTimer(registry, "demo.work", "IllegalArgumentException");

            service.selfInvoke();
            new WorkService(clock).work(false);
            System.out.println("after bypass: timed.count=" + timerCount(registry, "demo.work"));

            service.event(false);
            try {
                service.event(true);
            } catch (IllegalArgumentException expected) {
                // Continue verification steps.
            }
            System.out.printf(Locale.ROOT, "events: success=%.0f failure=%.0f%n",
                    registry.get("demo.events").tag("result", "success").counter().count(),
                    registry.get("demo.events").tag("result", "failure").counter().count());

            service.failuresOnly(false);
            try {
                service.failuresOnly(true);
            } catch (IllegalStateException expected) {
                // Only this failure is counted.
            }
            System.out.printf(Locale.ROOT, "failures.only=%.0f success.series.present=%s%n",
                    counterCount(registry, "demo.failures"),
                    registry.find("demo.failures").tag("result", "success").counter() != null);

            CompletableFuture<String> source = new CompletableFuture<>();
            CompletableFuture<String> observed = service.await(source);
            System.out.printf(Locale.ROOT, "async before: timed=%d counted=%.0f%n",
                    timerCount(registry, "demo.async"),
                    counterCount(registry, "demo.async.completed"));
            clock.add(Duration.ofMillis(25));
            source.complete("done");
            System.out.println("async result=" + observed.join());
            printTimer(registry, "demo.async", "none");

            CompletableFuture<String> failedSource = new CompletableFuture<>();
            CompletableFuture<String> failedObserved = service.await(failedSource);
            clock.add(Duration.ofMillis(7));
            failedSource.completeExceptionally(new IllegalStateException("Async failure"));
            try {
                failedObserved.join();
            } catch (CompletionException expected) {
                // Caller still observes the error via the returned future.
            }
            printTimer(registry, "demo.async", "IllegalStateException");
            System.out.printf(Locale.ROOT, "async after: timed=%d counted=%.0f%n",
                    timerCount(registry, "demo.async"),
                    counterCount(registry, "demo.async.completed"));
        }
    }

    private static long timerCount(MeterRegistry registry, String name) {
        return registry.find(name).timers().stream().mapToLong(Timer::count).sum();
    }

    private static double counterCount(MeterRegistry registry, String name) {
        return registry.find(name).counters().stream().mapToDouble(counter -> counter.count()).sum();
    }

    private static void printTimer(MeterRegistry registry, String name, String exception) {
        Timer timer = registry.get(name).tag("exception", exception).timer();
        System.out.printf(Locale.ROOT, "%s exception=%s count=%d total.ms=%.0f%n",
                name, exception, timer.count(), timer.totalTime(TimeUnit.MILLISECONDS));
    }
}
```

Run using an installed Gradle, or the experiment project's wrapper if present:

```shell
gradle -q run
```

To test directly with `javac`/`java`, first run `gradle -q copyRuntimeDependencies`, then run on Windows:

```shell
javac --release 17 -encoding UTF-8 -parameters -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/MetricsAspectDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.MetricsAspectDemo
```

On Linux/macOS, replace `;` separating classpath entries in the `java` command with `:`.

### 5.3. Program Stdout

```text
proxy=true
demo.work exception=none count=1 total.ms=10
demo.work exception=IllegalArgumentException count=1 total.ms=5
after bypass: timed.count=2
events: success=1 failure=1
failures.only=1 success.series.present=false
async before: timed=0 counted=0
async result=done
demo.async exception=none count=1 total.ms=25
demo.async exception=IllegalStateException count=1 total.ms=7
async after: timed=2 counted=2
```

`Locale.ROOT` keeps numeric formatting consistent. The mock clock advances only the time observed by meters; the program does not actually sleep for 10, 25, or 7 milliseconds. Closing the Spring context also closes beans with corresponding lifecycles.

## 6. Explaining Each Piece of Evidence

### 6.1. Proxy Present, Aspect Present, Metrics Recorded

`proxy=true` proves the bean retrieved from the context is an AOP proxy. However, having a proxy alone is not enough proof that measurement is active: a bean can be proxied for transactions without having TimedAspect. Complete proof is calling through the proxy plus seeing the expected meter and values after the call.

Two calls to `work` through the proxy create two timer series by the `exception` tag:

| Outcome | Exception tag | Count | Total duration |
| --- | --- | --- | --- |
| Completed normally | `none` | 1 | 10 ms |
| Threw exception | `IllegalArgumentException` | 1 | 5 ms |

Standard timers record both successful calls and calls ending with an exception. The aspect does not swallow business exceptions: the caller still catches `IllegalArgumentException`.

If you want total executions, sum counts across series matching the intended name and scope. Reading only `exception=none` counts only normal completions.

### 6.2. Two Bypassed Calls Still Run Business Logic Without Being Measured

Next, the program invokes:

```java
service.selfInvoke();
new WorkService(clock).work(false);
```

The first call enters `selfInvoke` through the proxy, yet the subsequent call to `work` executes on the target object directly. The second call invokes a directly instantiated object. Both advance the mock clock, yet the `demo.work` timer keeps a total count of 2.

Missing metrics do not mean business logic did not run. This is why you must trace the call path when an annotation “appears to do nothing.”

### 6.3. @Counted Classifies by Method Completion

In the example:

```text
event(false) -> result=success, exception=none
event(true)  -> result=failure, exception=IllegalArgumentException
```

Each series has a count of 1. “Success” here means **the method/aspect observed normal completion**, not automatic validation of all business success criteria.

For instance, a method returning `false`, returning an HTTP response with an error code as a normal value, or catching an exception to return a fallback result may still be treated by the aspect as success. To count business states such as “payment declined” without exceptions, record metrics by explicit business state rather than inferring from the `result` tag.

### 6.4. recordFailuresOnly Does Not Pre-Create a Success Counter at 0

`failuresOnly(false)` does not increment a counter. `failuresOnly(true)` creates/increments the failure counter to 1. In the freshly run program, no `result=success` series exists for this meter:

```text
failures.only=1 success.series.present=false
```

Distinguish “meter/series does not exist yet” from “series exists with value 0.” This distinction affects dashboard queries, especially before the first execution.

## 7. Asynchronous Methods: Waiting for Completion or Only Method Return?

A method can return a future very quickly while the actual work finishes only later. Measuring only until return can reflect just future creation/scheduling time.

For return types declared as `CompletionStage` or a subtype such as `CompletableFuture`, the aspects used in this lesson attach completion handling to the stage:

```text
Call through proxy
    -> capture start timestamp
    -> method returns pending future
    -> no completion recorded yet
    -> future completes normally or with error
    -> record timer/counter by outcome
```

In the experiment, `await` does not spawn a new thread itself; it returns the future supplied by the caller. This cleanly separates **asynchronous result lifecycle** from **thread scheduling**.

| Moment | Timer count | Counter count | Meaning |
| --- | --- | --- | --- |
| After obtaining first future, still pending | 0 | 0 | No completion yet |
| After first future completes normally | 1 | 1 | Success timer has 25 ms |
| After second future completes with error | 2 | 2 | Adds 7 ms error timer |

The program waits on **the future returned from the proxy** using `join()`, ensuring the completion callbacks attached to the returned chain have run before reading metrics. Do not assume the returned future object is reference-identical to the internal future, because the aspect may return a chained stage.

### Limitations to Check

- **Declared return type in the signature matters.** If the signature returns `Object` or only `Future`, do not assume the aspect recognizes `CompletionStage` lifecycle even if the runtime object relates to async processing.
- **Future that never completes:** standard completion timers/counters receive no sample. To monitor active in-flight work, choose a meter suited for that state.
- **Cancelling a future:** usually manifests as exceptional completion/exception; check how your specific version and cancellation path classify it before building alerts.
- **Reactor Mono/Flux:** do not assume the aspects above wait for publisher completion. Reactive streams have their own subscription lifecycle and require metrics tied to that lifecycle.
- **`@Async`:** is a separate execution-scheduling mechanism. Using it requires the corresponding async configuration; adding `@Timed` does not create an executor or run the method on a background thread.

In the example, the failure completed with `IllegalStateException`; the verified output carried the matching tag. Do not assume exception wrappers across every async path are unwrapped identically: check actual names/tags in the registry when writing queries.

## 8. Annotations Must Match the Meter Type and Readings Needed

### 8.1. Standard Timer and Long-Task Timer Answer Different Questions

By default `@Timed` uses a completion timer. Configuring:

```java
@Timed(value = "app.catalog.rebuild.active", longTask = true)
```

selects a `LongTaskTimer` for the annotated method. It is useful when you need to know how many long tasks are currently active and their current elapsed duration, not a historical completion count comparable to a standard timer.

Do not read a `LongTaskTimer` assuming `Timer.count()` semantics or mix it under the same name as a standard timer. When you need both completion history and running status, design two meters with clear names and purposes.

### 8.2. Enable Percentiles or Histograms Deliberately

Example declaration when duration distribution is actually needed:

```java
@Timed(
    value = "app.search.execute",
    histogram = true,
    percentiles = {0.50, 0.95}
)
```

This illustrates properties available on the Micrometer annotation used in this lesson. Histograms serve distribution analysis in supported monitoring backends; client-computed percentiles cannot be simply averaged to get a multi-instance p95. Enabling extra statistics increases cost, so select based on the observability question rather than enabling everything on every method.

### 8.3. Composed Annotations and Tags from Parameters

Do not wrap `@Timed`/`@Counted` inside custom annotations expecting the base aspect to recognize every meta-annotation automatically. Micrometer 1.13 documentation notes limits on this support; the easiest approach to verify is placing the aspect-supported annotation directly on the target method.

`@MeterTag` also does not automatically guarantee a parameter becomes a tag. With TimedAspect, an appropriate `MeterTagAnnotationHandler` must be configured. That is a separate extension; the main example uses only fixed `extraTags` to bound series counts and focus on verifying the aspect mechanism.

If adding tags from parameters, normalize them to a finite set such as task type or classification outcome. Creating a new series per request ID grows series count with data volume.

## 9. Aspect Ordering Determines Measurement Meaning

Alongside metrics, the same method may be affected by retries, transactions, async execution, or other interceptors.

For example, with retries:

```text
Timer outside Retry:
    timer starts -> attempt 1 -> attempt 2 -> success -> timer stops
    => one overall operation

Timer inside Retry:
    attempt 1 -> timer attempt 1
    attempt 2 -> timer attempt 2
    => two attempts
```

Both approaches can be valid yet answer different questions. Similarly, placement relative to transactions affects whether commit time is included in the measurement and whether commit failures are observed at that boundary. Placement relative to async affects the visible time span, such as scheduling wait time.

Do not rely on annotation order in source code to deduce advice order. When multiple mechanisms interact, check proxy/advisor configuration and test a scenario with deterministic outcomes. When needing to distinguish “whole operation” from “per attempt,” name the meters after those two exact boundaries.

The experiment's numbers do not depend on relative ordering between TimedAspect and CountedAspect: on the async method, both ultimately observe completion of the result chain. When business methods carry additional interceptors, verify the actual boundary again.

## 10. Verifying via Actuator and Diagnosing Missing Metrics

In a Spring Boot web application with the aspect configuration integrated, you can expose the metrics endpoint in local config:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

After invoking a business method through an injected bean, inspect using the **Micrometer name in code**, not the Prometheus-converted name:

```shell
curl "http://localhost:8080/actuator/metrics/app.invoice.generate"
curl "http://localhost:8080/actuator/metrics/app.invoice.generate?tag=exception:none"
```

These are verification requests against an application having a method with the corresponding meter name, not an endpoint created automatically by the plain-Spring program. Address, port, base path, and authentication requirements depend on the running application.

The registry typically contains the meter only after a matching recording has occurred. For async timers, complete the work before looking for completion metrics. Filter by `exception`, `method`, or verified tags to inspect the exact series.

| Symptom | Check first | Fix direction |
| --- | --- | --- |
| Annotation exists yet no meter appears | Are TimedAspect/CountedAspect beans present and is AOP active? | Add missing configuration, use the application registry |
| Bean is a proxy yet still no metrics | Does the proxy have the right metrics aspect advisor? | Do not treat proxy presence alone as sole proof |
| Only external calls are measured | Is there self-invocation? | Place the boundary on the outer method or an appropriate collaborator bean |
| Object runs yet emits no metrics | Is the caller using `new`? | Use the Spring-injected bean reference |
| Enabling class-based proxy fails startup | Is the class final or unproxiable? | Choose proxy-compatible class/method structure or check interface proxying |
| Success counter increments when business logic fails | Does the method throw an error or merely return a value? | Define metrics by the business state you need to count |
| Async timer is too short | Return signature, stage lifecycle, and advisor boundary | Track the right stage or measure directly on the real lifecycle |
| Recording count doubles | Aspect registered multiple times or another instrumentation already active | Keep exactly one mechanism per boundary |
| Actuator misses metrics while another registry has them | Was a private registry created outside the exported one? | Use the injected registry consistently |

HTTP servers, clients, or libraries with their own built-in instrumentation may measure boundaries different from services. Before placing aspects broadly across controllers or the whole application, inspect existing metrics to avoid duplicate measurements or naming collisions across meter types. [Spring Boot 3.3 Metrics documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint) explains reading the endpoint by name and tags.

## 11. Practice to Verify Understanding of the Mechanism

1. **Remove the TimedAspect bean in the experiment while keeping CountedAspect.** Counters continue to work, while timer lookups find no meter. This separates “AOP works” from “the right aspect is registered.”
2. **Put @Timed on selfInvoke with a different name.** An external call to selfInvoke creates a timer for the outer method; the `demo.work` timer still does not increment from the internal call. Explain why there is no contradiction.
3. **Call event(false) three times and event(true) once on a fresh context.** Expect success counter = 3 and failure counter = 1. If the failing method is changed to return `false` normally, re-evaluate the meaning of the `result` tag.
4. **Obtain the future and leave it uncompleted.** Confirm no completion exists yet; then complete it and wait on the future returned by the proxy before reading count.
5. **Compare counting needs with timing needs.** If a timer already answers both duration and completion count, explain why a counter sharing the exact same boundary can be omitted.

The goal is identifying which annotation is processed by which aspect, which calls truly pass through the proxy, and what moment counts as completion. Only when those three are clear do metrics carry reliable meaning for testing and operations.
