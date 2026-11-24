# Using @Observed with the Aspect Mechanism to Observe Methods

## 1. What Does Observing a Business Operation Mean?

Suppose the application already measures HTTP handling duration, yet you need to know separately how many times the pricing calculation runs, how long it takes, and whether it throws exceptions. The HTTP boundary covers many tasks; a measurement at a business method makes the pricing portion visible within the overall request.

`@Observed` belongs to Micrometer, with the fully qualified name `io.micrometer.observation.annotation.Observed`. This annotation declares that a method or matching methods of a class should be wrapped in an `Observation`. It does not run measurement logic by itself.

The components collaborate as follows:

| Component | Role in the call |
| --- | --- |
| `@Observed` | Supplies the name and tags describing the operation |
| `ObservedAspect` | Intercepts matching calls, manages the observation lifecycle, and invokes the real method |
| Spring AOP proxy | Intermediary object the caller must go through for the aspect to execute |
| `ObservationRegistry` | Holds observation configuration, handlers, and the current active observation context |
| `ObservationHandler` | Reacts to the observation lifecycle; depending on configuration, may record metrics, create spans, or handle other events |

An annotation only turns into observation data when this chain is wired properly. A metrics handler may create a `Timer`; a tracing handler may create a span. Simply adding `@Observed` does not mean data has been sent to Prometheus or a tracing system. [Micrometer explains Observation components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

Choose a meaningful operation such as pricing, reviewing applications, or generating reports. There is no need to annotate every helper function. If the system already observes that exact operation, inspect existing data before adding another measurement layer.

## 2. How Does the Aspect Wrap a Method?

With a synchronous method and normal configuration, you can picture the execution flow:

```text
Caller
  -> Spring AOP proxy
     -> ObservedAspect creates and starts observation
     -> opens scope for the call
     -> business method
        -> returns result or throws exception
     -> records error if exception escapes
     -> closes scope and stops observation
  -> returns result or forwards exception to caller
```

Scope is the boundary within which the observation is considered current. During a synchronous call, code running inside that scope can look up the current observation via the registry. If a parent observation is already in context, the new observation can sit beneath it; whether it renders as a span tree also depends on tracing configuration.

The aspect does not turn the business outcome into an observation object. If the method returns `42`, the caller still receives `42`; an escaping business exception still must be handled by the caller. The observation must finish on both success and failure, and the scope must be restored after the call. [Lifecycle and scope in Micrometer](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

Two distinctions to remember:

- If the method catches an exception itself and returns a normal value, the aspect does not automatically know business logic failed. A return value like `false` or a "rejected" status also does not automatically become a technical error.
- Having an observation in memory, having a metric in the registry, and having data in the monitoring system are three distinct verification levels. Do not infer the final level merely because the annotation was recognized.

## 3. Integrating into a Spring Boot Application

### 3.1. Required Conditions

In a Spring Boot 3.3.x application, ensure:

1. Micrometer Observation and an `ObservationRegistry` wired to Actuator infrastructure are present.
2. Spring AOP and the AspectJ runtime required for the aspect are present.
3. Exactly one matching `ObservedAspect` uses the application's registry.
4. The method belongs to a Spring-managed bean and the call goes through the proxy.

For a project already using Spring Boot's plugin/BOM, the Gradle dependencies typically needed are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

This is an addition to an existing Boot application's build configuration, not a complete `build.gradle`. Let Boot manage compatible Micrometer, Spring, and AspectJ versions; do not arbitrarily mix individual versions into an existing module.

### 3.2. Registering the Aspect When Configuring Manually

You can use the following configuration within the application's scan scope:

```java
package example.observed;

import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ObservationMethodConfig {
    @Bean
    @ConditionalOnMissingBean(ObservedAspect.class)
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
```

If the application already has an `ObservedAspect` from shared configuration or auto-configuration, use that bean. `@ConditionalOnMissingBean` prevents this configuration from proactively adding a second bean of the same type if one already exists. Inspect actual configuration to avoid registering multiple aspects via different paths.

The way this example activates the aspect is by declaring the bean directly. Do not assume a configuration property exists in every Boot version, or set a single property and skip verifying the bean/proxy. Auto-configuration conditions must be checked against the exact version running. [Spring Boot 3.3.5 Observation auto-configuration code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationAutoConfiguration.java).

With the AOP starter and AOP auto-configuration enabled, Boot can create proxies for matching beans. If `spring.aop.auto` was disabled or the AOP setup was changed, recheck it. In a plain Spring application, you can enable proxying with `@EnableAspectJAutoProxy`, as in the standalone experiment below.

Inject the Boot-managed registry into the aspect. Do not create an extra `ObservationRegistry.create()` in production configuration just to pass to the aspect: a separate registry may lack the handlers Boot configured. Creating a registry manually in the standalone example below is to show each piece of the experiment clearly.

### 3.3. Annotating the Method and Calling Through the Bean

Example `PricingService.java` in a Boot application:

```java
package example.observed;

import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    @Observed(name = "pricing.quote", contextualName = "calculate-price",
            lowCardinalityKeyValues = {"channel", "web"})
    public int quote(boolean fail) {
        if (fail) {
            throw new IllegalArgumentException("invalid input");
        }
        return 42;
    }
}
```

Another bean receives `PricingService` via constructor injection and calls `pricingService.quote(false)`. That is the proper call path to go through the proxy. Do not replace the injected dependency with `new PricingService()`.

This service snippet belongs inside an existing Boot application; it has no `main` of its own and does not boot the application. The aspect configuration above and the service must both lie within Spring's component-scan scope.

## 4. Naming and Tagging the Observation

In the example:

```java
@Observed(name = "pricing.quote", contextualName = "calculate-price",
        lowCardinalityKeyValues = {"channel", "web"})
```

- `name` is the stable technical name of the observation, suitable for grouping metrics.
- `contextualName` describes the operation in context, useful when a tracing handler creates span names. It is not an alternate name for metrics.
- `lowCardinalityKeyValues` consists of consecutive key–value pairs: `"channel", "web"`. The element count must be even.
- The default aspect also provides tags such as `class` and `method`; account for these tags when analyzing metric series.

Low-cardinality tags should describe stable groups: calling channel, operation type, or normalized outcome category. Each tag combination can create another metric series. Do not use order IDs, UUIDs, email addresses, tokens, or request payloads as metric tags.

Values in the annotation are Java string constants. Writing `"channel", "#channel"` does not automatically make `@Observed` read a `channel` parameter with SpEL; without a dedicated extension mechanism, that is literally the declared string value.

When you need tags based on runtime data or a measurement scope narrower than the whole method, consider the programmatic Observation API or an appropriate convention. Illustrative example inside a method that already has the needed variables:

```java
return Observation.createNotStarted("pricing.quote", registry)
        .lowCardinalityKeyValue("channel", normalizedChannel)
        .observe(() -> calculatePrice(input));
```

Here `registry`, `normalizedChannel`, `input`, and `calculatePrice` belong to the surrounding business code, not a standalone program. `normalizedChannel` must be normalized into a bounded value set.

In standard Boot infrastructure, low-cardinality tags are used for metrics and traces; high-cardinality tags are not turned into metric tags by the default metrics handler. That does not make sensitive data appropriate to collect. [Tag classification in Spring Boot Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 5. Proxy Limitations and Common Misunderstandings

### 5.1. Self-Invocation Bypasses the Aspect

If the same object calls `this.quote(false)`, the call goes straight to the target object. The annotation on `quote` is not intercepted again simply because that method carries the annotation.

```java
public int forward() {
    return this.quote(false);
}
```

If an external caller invokes `forward()` through the proxy while `forward` is not observed and `quote` is only called via `this`, there will be no observation for `quote`. If `forward` is also observed, an observation for `forward` still does not prove the internal call to `quote` was intercepted separately by the aspect.

The clearest solution is usually moving the operation to observe into another bean and injecting that bean. If you only need to observe a block inside a method, use the programmatic API for that block. Avoid contorting design just to reach the proxy via roundabout self-calls.

### 5.2. Method Visibility and Proxy Type Matter

| Case | What to check |
| --- | --- |
| Object created directly with `new` | Normally unproxied; annotation has no effect on its own |
| `private` or `static` method | Not a call intercepted by Spring AOP proxies in this manner |
| `final` class when using class proxies | CGLIB cannot subclass it to create a proxy |
| `final` method when using class proxies | Cannot be overridden for CGLIB interception |
| JDK proxy | Calls are intercepted through interfaces provided by the proxy; CGLIB override limits do not apply identically |
| Called in constructor or too early during initialization | Do not assume the object is already ready to be called via proxy |

To start safely, use a `public`, non-`final` method on a non-`final` class, place the annotation directly on the implementing method, and invoke through the injected bean. This reduces subtle differences across proxy types. Class-level annotations are also subject to interception limits; they do not turn internal self-calls into proxied calls. [Spring Framework explains proxies and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

### 5.3. Async and Reactive Methods Need Separate Verification

Do not mechanically apply the synchronous diagram to every return type. `ObservedAspect` in Micrometer 1.13.0 has special handling for methods declared to return `CompletionStage`: the observation stops when the stage completes. That differs from measuring only until the method returns a future object.

Still, do not infer that the current observation automatically propagates to every thread or callback. With `@Async`, aspect ordering and thread-switching boundaries also affect observation scope.

Similarly, a method returning `Mono` or `Flux` may only assemble an unexecuted pipeline. Do not use the presence of `@Observed` as proof that all subscriptions, errors, and cancellations are measured properly. Use Reactor/Observation integration and tests matching the library in use. This lesson focuses on synchronous methods; other boundaries require dedicated experiments.

## 6. Standalone Experiment, Runnable with JDK 21

The following experiment uses Spring Framework 6.1.8, Micrometer 1.13.0, and AspectJ 1.9.22, matching the Boot 3.3.0 library generation. Versions are pinned to reproduce the experiment; in a Boot application, continue using Boot's dependency management.

The program uses a Spring context and bean proxies without starting a web server. Thus, no HTTP endpoint or external monitoring system is needed to verify the aspect mechanism.

### 6.1. Preparing Dependencies

In a dedicated experiment directory, create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>observed-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.8</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

`micrometer-core` brings in the needed Micrometer Observation dependencies; Maven resolves the remaining transitive dependencies.

### 6.2. Complete ObservedDemo.java Program

Save in the same directory as `pom.xml`, with no package declaration:

```java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.annotation.Observed;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class ObservedDemo {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var service = context.getBean(PricingService.class);
            var recorder = context.getBean(Recorder.class);
            var registry = context.getBean(ObservationRegistry.class);
            var meters = context.getBean(SimpleMeterRegistry.class);

            System.out.println("raw=" + new PricingService().quote(false));
            System.out.println("after.raw=" + recorder.stops);
            System.out.println("proxied=" + service.quote(false));
            System.out.println("after.proxied=" + recorder.stops);
            System.out.println("self=" + service.forward());
            System.out.println("after.self=" + recorder.stops);

            try {
                service.quote(true);
            } catch (IllegalArgumentException ex) {
                System.out.println("error=" + ex.getClass().getSimpleName());
            }

            System.out.println("starts=" + recorder.starts);
            System.out.println("stops=" + recorder.stops);
            System.out.println("errors=" + recorder.errors);
            System.out.println("success.count=" + meters.get("pricing.quote")
                    .tag("error", "none").timer().count());
            System.out.println("failure.count=" + meters.get("pricing.quote")
                    .tag("error", "IllegalArgumentException").timer().count());
            System.out.println("current.cleared="
                    + (registry.getCurrentObservation() == null));

            if (recorder.starts != 2 || recorder.stops != 2
                    || recorder.errors != 1
                    || registry.getCurrentObservation() != null) {
                throw new AssertionError("Unexpected observation lifecycle");
            }
        }
    }

    public static class PricingService {
        @Observed(name = "pricing.quote", contextualName = "calculate-price",
                lowCardinalityKeyValues = {"channel", "demo"})
        public int quote(boolean fail) {
            if (fail) {
                throw new IllegalArgumentException("invalid input");
            }
            return 42;
        }

        public int forward() {
            return this.quote(false);
        }
    }

    public static class Recorder implements ObservationHandler<Observation.Context> {
        int starts;
        int stops;
        int errors;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return "pricing.quote".equals(context.getName());
        }

        @Override
        public void onStart(Observation.Context context) {
            starts++;
        }

        @Override
        public void onStop(Observation.Context context) {
            stops++;
        }

        @Override
        public void onError(Observation.Context context) {
            errors++;
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class Config {
        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        Recorder recorder() {
            return new Recorder();
        }

        @Bean
        ObservationRegistry observationRegistry(
                SimpleMeterRegistry meters, Recorder recorder) {
            var registry = ObservationRegistry.create();
            registry.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(recorder);
            return registry;
        }

        @Bean
        ObservedAspect observedAspect(ObservationRegistry registry) {
            return new ObservedAspect(registry);
        }

        @Bean
        PricingService pricingService() {
            return new PricingService();
        }
    }
}
```

`Recorder` is merely a counter for a single-threaded experiment. It is not a metric collector for multi-threaded applications. `DefaultMeterObservationHandler` is what connects observations to `SimpleMeterRegistry`.

### 6.3. Compiling and Running on PowerShell

JDK 21 must be active for both `javac` and `java`, along with Maven. The first run requires access to dependency repositories:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ObservedDemo.java
java -cp ".;$demoClasspath" ObservedDemo
```

Run each step only after the previous one succeeds. `;` in the classpath is the Windows separator; Linux/macOS uses `:`.

Program stdout, excluding Maven dependency download messages:

```text
raw=42
after.raw=0
proxied=42
after.proxied=1
self=42
after.self=1
error=IllegalArgumentException
starts=2
stops=2
errors=1
success.count=1
failure.count=1
current.cleared=true
```

### 6.4. Explaining Each Result

| Evidence | Meaning |
| --- | --- |
| `raw=42`, `after.raw=0` | Business code still runs when instantiating the object directly, but no aspect manages observations |
| `proxied=42`, `after.proxied=1` | The bean retrieved from the context was called through a proxy; the observation finished and the return value is still 42 |
| `self=42`, `after.self=1` | Internal self-invocation from `forward` to `quote` created no additional observation |
| `error=IllegalArgumentException` | The exception from the method propagated out to the caller |
| `starts=2`, `stops=2`, `errors=1` | Both direct proxied calls to the method finished; one call had an error |
| `success.count=1`, `failure.count=1` | The metrics handler created two timers by error tag; each recorded once |
| `current.cleared=true` | After the calls, no current observation remains held on the thread's context |

Do not predict a fixed timing value for the timer because duration depends on the machine and run. The exercise verifies recording counts and lifecycle rather than assigning a guessed duration number.

Each timer already has a recording count (`count`), so if you only need the call count for this exact operation, you do not necessarily have to add a separate counter.

## 7. Verifying in a Real Boot Application

The standalone experiment proves the Spring proxy + Micrometer aspect mechanism. When bringing it into an application, still check the actual call paths and configuration:

1. Obtain the service from the Spring context or inject it into another bean; do not construct the service with `new` when testing proxied call paths.
2. Confirm the context has the aspect with the right registry. You can use `AopUtils.isAopProxy(service)` to verify the object is a proxy, though `true` alone does not prove `ObservedAspect` itself ran.
3. Run one successful call and one exception-throwing call; confirm the observation name, tags, error, and stopped state.
4. Check `MeterRegistry` to confirm the metrics handler recorded data. For tracing, check the bridge, exporter, sampling config, and actual span data separately.
5. Check for no leaked scopes and no double-counting when adding a new observation to an already-instrumented call path.

You can use `micrometer-observation-test` and `TestObservationRegistry` to write assertions about observations instead of the illustrative counter. The test must pass that same registry to the aspect and still call through the proxy. The library supports asserting names, tags, errors, started/stopped states, and current observation. [Micrometer Observation testing guide](https://docs.micrometer.io/micrometer/reference/1.13/observation/testing.html).

When using `@SpringBootTest` or slice tests, distinguish test configuration from production configuration. For instance, trace senders and external metric-exporting registries are not automatically configured identically to production; `@AutoConfigureObservability` plays a role depending on test type. Do not conclude "the aspect is broken" just because no data shows up in an external monitoring system during a test. [Spring Boot: testing observability](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

If the web application already has Actuator HTTP endpoints and explicitly exposes `metrics`, you can use the metrics endpoint to inspect figures after actually calling the method. `@Observed` itself neither creates HTTP endpoints nor enables management endpoint exposure.

## 8. Common Mistakes and How to Isolate Them

| Symptom | Checks and resolution direction |
| --- | --- |
| Annotation present yet no observation data | Check aspect, AOP, bean proxy, registry, and handlers; do not check dependencies alone |
| Calling directly produces data, calling from same class does not | Review self-invocation; consider a separate bean or the programmatic API |
| Proxy exists yet expected observation is missing | Proxy might belong to transactions or another mechanism; verify the aspect and matched method |
| Observation runs yet no metric appears | Check metrics handler, meter registry, and the name/tags used when querying the timer |
| Metric exists yet no trace in backend | Check tracing infrastructure and export; that is a step downstream of the annotation mechanism |
| Count exceeds expected operations | Look for duplicate aspects, `@Timed` measuring the same operation, or layering over existing instrumentation |
| No error appears even though business rejected | Distinguish escaping exceptions from normal business return values or caught exceptions |
| Metric series count grows rapidly | Check whether tags or metric names contain dynamic values like UUIDs/order IDs |

A business observation inside an HTTP observation can be intentional and sensible: they answer two different questions. Conversely, adding two measurements on the exact same boundary with no clear purpose can make data hard to interpret. Do not sum durations of parent–child observations and treat that as request processing time.

## 9. Self-Check Exercises

1. Run the original program and verify every stdout line.
2. Remove the annotation from `quote`, keep the method calls, and predict the observation count. Once timers are no longer created, `meters.get(...).timer()` calls must also be removed or replaced with lookups that allow missing results; do not mistake a timer lookup failure for a business error.
3. Replace `forward()` with a call to a separate injected pricing bean. Verify the observation count increases as predicted.
4. Have `quote(true)` catch the exception and return a fallback value. Explain why the aspect does not automatically mark an error if the exception does not escape.
5. Pick a real business method, choose a stable name, pick a tag with a bounded value set, and write tests for both success and exception outcomes.

After each change, reason through the call path via the proxy and the observation lifecycle, rather than looking solely at the annotation in source code.
