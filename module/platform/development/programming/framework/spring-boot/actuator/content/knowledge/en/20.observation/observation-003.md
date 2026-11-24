# Creating an Observation for a Business Operation

## 1. Observing Something Meaningful to the Business

An Observation is an observation of an activity with start and end boundaries, along with an operation name, descriptive metadata, and any error. When we instrument a business operation with an Observation, we want to know how many times that operation was called, how long it took, how it failed, and where it sits in an execution trace.

For example, an inventory service receives a request to reserve two items for an order. An HTTP request may also do many other things, so metrics for the entire request do not answer questions about the inventory reservation step on its own. An observation named `stock.reserve` placed at the service layer directly represents the question: **how did a valid inventory reservation attempt execute?**

Instrumentation code emits lifecycle events; handlers (`ObservationHandler`) decide whether to create measurements, spans, or additional handling. Therefore, business code does not need to know the address of any monitoring server. In Spring Boot, you can inject `ObservationRegistry` to create custom observations. [Source: Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

This lesson uses the API directly, without requiring annotations or AOP to observe methods. The example runs with Spring Boot 3.3.0 and Java 17 or newer, starting as an application without a web server.

## 2. Choose the Boundaries Before Writing Code

### 2.1. Where Does It Start, and Where Does It End?

Before creating an observation, decide:

- Does one recording represent a valid invocation, a single retry attempt, or the entire business request?
- Does input validation fall inside the observation interval?
- Which cases count as errors, and which are normal rejection outcomes?
- Which classification dimensions are useful for aggregating metrics?

In this lesson's example:

```text
reserve(sku, quantity, channel)
    → validate input
    → start observation stock.reserve
    → read available quantity
    → enough stock: deduct inventory and return result
      insufficient stock: throw OutOfStockException
    → stop observation in both cases
```

An input with quantity 0 is rejected before the observation. A request with valid input but insufficient stock falls inside the observation. This is the example's measurement definition choice, not a mandatory rule for every system.

If you want to count malformed requests as well, move the corresponding validation inside the boundary or create a separate meaningful measurement. Do not move validation arbitrarily while keeping the old interpretation of the numbers.

### 2.2. Place It at the Layer Containing the Operation to Measure

Observing inside the service ensures the same operation is recorded whether called from HTTP, a background job, or a CLI program. An outer layer can measure the overall workflow; a child observation can measure a specific step. Those two boundaries should have distinct names and meanings.

Do not wrap a new observation around every tiny method just to generate more data. Start with operations that operators genuinely need to distinguish: reserving inventory, pricing, confirming payment, or generating documents.

## 3. Preparing the Registry and Descriptive Data

### 3.1. Use the Spring-Managed ObservationRegistry

In a Boot application with Actuator, the service receives `ObservationRegistry` via its constructor. There is no need to create a new registry for each invocation. Boot creates the registry bean when needed and configures handlers and observation components via bean post-processing. [Source: ObservationAutoConfiguration 3.3.0](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationAutoConfiguration.java).

Key distinctions:

| Object | How to use it |
| --- | --- |
| `ObservationRegistry` | Shared according to application configuration, injected into services |
| `Observation` | Created fresh for each execution of the operation |
| `Observation.Context` | Data of a single observation run, used by handlers |
| `MeterRegistry` | Manages measurements; does not replace ObservationRegistry |

If you call `ObservationRegistry.create()` yourself inside a service, that standalone registry will not automatically inherit the configuration present on Boot's bean. Your code may still run, yet lack the handlers needed to produce the expected data.

Do not hold an active `Observation` object in a singleton field and reuse it across requests. Names and conventions can be shared; the lifecycle, errors, and data of each invocation must be independent.

### 3.2. Stable Names, Bounded Tags

Design for the stock reservation operation:

| Element | Value in example | Purpose |
| --- | --- | --- |
| Observation name | `stock.reserve` | Identifies the same operation type across many calls |
| Contextual name | `reserve-stock` | Human-readable name for handlers that use contextual names, such as tracing |
| Low-cardinality tag | `channel=web` or `channel=mobile` | Aggregates by calling channel with a small value set |
| High-cardinality tag | `sku=SKU-A` | Specific lookup detail, not a default metric tag |

Cardinality is the number of values or tag combinations that can occur. Using an enum for `channel` constrains the value set right in the example API. Do not use arbitrary caller-supplied strings as low-cardinality tags without normalization.

Do not name it `stock.reserve.SKU-A`, creating a new name for every product code. Likewise, do not add a request ID or trace ID to metric tags just to locate a specific call.

In the standard processing pipeline, low-cardinality tags can go to both metrics and traces; high-cardinality tags are not used as default metric tags. High-cardinality tags still must be chosen selectively—they are not a place to dump entire requests or secrets. [Source: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 4. Using observe to Manage the Lifecycle and Return Values

The key part in the example service is creating an observation in the unstarted state, attaching known metadata, and calling `observe(...)`. For tasks that return a value, the overload accepting `Supplier<T>` returns the task's result.

`observe(...)` manages starting, opening the context scope, running the task, recording errors when the task throws, closing the scope, and stopping the observation. As a result, both the success path and the exception path pass through cleanup. [Source: Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).

From the service method's perspective:

- If the task returns a `Reservation`, the method continues returning that result.
- If the task throws `OutOfStockException`, the exception propagates outward; Observation does not turn it into a success value.
- Recording an error does not automatically undo data changes and does not replace transaction management.

Known tags should be attached before starting. Some handlers create measurements right at start time, so adding tags late does not guarantee they appear on every active measurement. [Source: DefaultMeterObservationHandler 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java).

## 5. Complete Spring Boot Program

### 5.1. What the Program Demonstrates

Initial stock has 3 units of `SKU-A`. The program makes four calls:

1. Web channel reserves 2 units: succeeds, 1 remaining.
2. Web channel tries to reserve 2 more units: insufficient stock, throws an error.
3. Web channel sends quantity 0: invalid input, rejected before observation.
4. Mobile channel reserves the remaining 1 unit: succeeds, 0 remaining.

Because of the chosen boundary, there are **three observations**, consisting of two successes and one business error. A small handler counts lifecycle events for verification; the metrics handler configured by Boot still handles measurements separately.

The example uses a `HashMap` on a single thread to keep the exercise self-contained. It does not simulate database transactions or resolve inventory contention across concurrent requests. There is no HTTP server, mock API, or connection to an external monitoring service.

### 5.2. File pom.xml

JDK 17 or newer and Maven are required. Create a dedicated practice directory and place `pom.xml` and `StockObservationApplication.java` side by side. Maven is used to download dependencies; the code is compiled with the `javac` command below.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>stock-observation-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
  </dependencies>
</project>
```

The parent manages compatible Spring Boot and Micrometer versions. No external registry is needed to inspect in-memory measurements. The first dependency download requires network access.

### 5.3. File StockObservationApplication.java

```java
package example.stock;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableAutoConfiguration
public class StockObservationApplication {
    static final String OBSERVATION_NAME = "stock.reserve";

    enum Channel { WEB, MOBILE }

    record Reservation(String sku, int quantity, int remaining) {}

    static final class OutOfStockException extends RuntimeException {
        OutOfStockException() {
            super("Not enough stock");
        }
    }

    static final class StockService {
        private final ObservationRegistry registry;
        private final Map<String, Integer> stock = new HashMap<>(Map.of("SKU-A", 3));

        StockService(ObservationRegistry registry) {
            this.registry = registry;
        }

        Reservation reserve(String sku, int quantity, Channel channel) {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(channel, "channel");
            if (sku.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("sku must be nonblank and quantity must be positive");
            }
            return Observation.createNotStarted(OBSERVATION_NAME, registry)
                .contextualName("reserve-stock")
                .lowCardinalityKeyValue("channel", channel.name().toLowerCase(Locale.ROOT))
                .highCardinalityKeyValue("sku", sku)
                .observe(() -> reserveInternal(sku, quantity));
        }

        private Reservation reserveInternal(String sku, int quantity) {
            int available = stock.getOrDefault(sku, 0);
            if (available < quantity) {
                throw new OutOfStockException();
            }
            int remaining = available - quantity;
            stock.put(sku, remaining);
            return new Reservation(sku, quantity, remaining);
        }
    }

    static final class LifecycleRecorder implements ObservationHandler<Observation.Context> {
        int starts;
        int errors;
        int stops;
        int scopeOpens;
        int scopeCloses;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return OBSERVATION_NAME.equals(context.getName());
        }

        @Override
        public void onStart(Observation.Context context) {
            starts++;
        }

        @Override
        public void onError(Observation.Context context) {
            errors++;
        }

        @Override
        public void onStop(Observation.Context context) {
            stops++;
        }

        @Override
        public void onScopeOpened(Observation.Context context) {
            scopeOpens++;
        }

        @Override
        public void onScopeClosed(Observation.Context context) {
            scopeCloses++;
        }
    }

    @Bean
    StockService stockService(ObservationRegistry registry) {
        return new StockService(registry);
    }

    @Bean
    LifecycleRecorder lifecycleRecorder() {
        return new LifecycleRecorder();
    }

    private static long count(MeterRegistry meters, String channel, String error) {
        return meters.get(OBSERVATION_NAME)
            .tags("channel", channel, "error", error).timer().count();
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(StockObservationApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
            "logging.level.root", "OFF",
            "management.metrics.use-global-registry", "false"));

        try (ConfigurableApplicationContext context = application.run(args)) {
            StockService stock = context.getBean(StockService.class);
            MeterRegistry meters = context.getBean(MeterRegistry.class);
            ObservationRegistry observations = context.getBean(ObservationRegistry.class);
            LifecycleRecorder lifecycle = context.getBean(LifecycleRecorder.class);

            Reservation first = stock.reserve("SKU-A", 2, Channel.WEB);
            System.out.println("first.remaining=" + first.remaining());

            try {
                stock.reserve("SKU-A", 2, Channel.WEB);
            } catch (OutOfStockException error) {
                System.out.println("rejected=" + error.getClass().getSimpleName());
            }

            try {
                stock.reserve("SKU-A", 0, Channel.WEB);
            } catch (IllegalArgumentException error) {
                System.out.println("invalid=" + error.getClass().getSimpleName());
            }

            Reservation last = stock.reserve("SKU-A", 1, Channel.MOBILE);
            System.out.println("last.remaining=" + last.remaining());
            System.out.println("web.success=" + count(meters, "web", "none"));
            System.out.println("web.failure=" + count(meters, "web", "OutOfStockException"));
            System.out.println("mobile.success=" + count(meters, "mobile", "none"));
            long total = meters.find(OBSERVATION_NAME).timers().stream()
                .mapToLong(Timer::count).sum();
            System.out.println("observed.total=" + total);
            boolean skuIsMetricTag = meters.find(OBSERVATION_NAME).timers().stream()
                .anyMatch(timer -> timer.getId().getTag("sku") != null);
            System.out.println("sku.isMetricTag=" + skuIsMetricTag);
            System.out.println("lifecycle=" + lifecycle.starts + "/"
                + lifecycle.errors + "/" + lifecycle.stops);
            System.out.println("scopes=" + lifecycle.scopeOpens + "/" + lifecycle.scopeCloses);
            System.out.println("current.cleared=" + (observations.getCurrentObservation() == null));
        }
    }
}
```

### 5.4. Compiling and Running

In PowerShell, in the directory containing the two files:

```powershell
mvn dependency:copy-dependencies -DincludeScope=runtime
New-Item -ItemType Directory -Force -Path target/classes | Out-Null
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes StockObservationApplication.java
java -cp "target/classes;target/dependency/*" example.stock.StockObservationApplication
```

The file declares package `example.stock`, so the full class name when running is `example.stock.StockObservationApplication`. With this direct `javac` invocation, `-d` creates the package directory under `target/classes`. In a standard Maven project, move the file into the `src/main/java/example/stock/` tree.

On Linux/macOS, create the directory with `mkdir -p target/classes` and use `:` instead of `;` between the two classpath entries in the `java` command.

The program disables the banner and startup logs so the hands-on stdout stays clear; this is not a requirement to disable logging in real applications. Running the example as-is, without adding configuration to disable observations or registries, yields stdout:

```text
first.remaining=1
rejected=OutOfStockException
invalid=IllegalArgumentException
last.remaining=0
web.success=1
web.failure=1
mobile.success=1
observed.total=3
sku.isMetricTag=false
lifecycle=3/1/3
scopes=3/3
current.cleared=true
```

### 5.5. Verifying Each Piece of Evidence

| Output | What is proven |
| --- | --- |
| `first.remaining=1` | The success branch returns the business result and updates inventory |
| `rejected=OutOfStockException` | The exception from the task still propagates to the caller for handling |
| `invalid=IllegalArgumentException` | Invalid input is blocked before the chosen observation boundary |
| `last.remaining=0` | The out-of-stock branch did not deduct inventory; the last call still reserved the remaining item |
| `web.success=1` | A timer tagged `channel=web`, `error=none` recorded one invocation |
| `web.failure=1` | The timer for the failing web branch recorded one invocation with the exception class name |
| `mobile.success=1` | Same operation name, but a different channel tag forms a separate aggregation group |
| `observed.total=3` | Total timer recordings equal the number of calls that actually entered observation |
| `sku.isMetricTag=false` | The high-cardinality tag does not become a default timer tag |
| `lifecycle=3/1/3` | The handler received 3 starts, 1 error, and 3 stops |
| `scopes=3/3` | All three scopes were opened and closed |
| `current.cleared=true` | After the calls, no current observation remains on the example's thread |

Micrometer 1.13's default timer adds the tag `error=none` when there is no error, or the simple class name of the exception when an error occurs. That is why the check looks for `OutOfStockException`, not the full exception message text. [Source: DefaultMeterObservationHandler](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java).

The program does not print fixed execution times because actual duration depends on the run. `Timer.count()` is the number of timing recordings, without requiring a separate Counter just to get the call count.

`sku.isMetricTag=false` only checks metric tags. The example installs no tracer or trace exporter, so do not use that result to claim that a span containing the SKU already exists on another server.

## 6. Why Does the Example Configuration Work?

`@Configuration` declares the exercise's beans; `@EnableAutoConfiguration` turns on Boot's auto-configuration mechanism. `StockService` receives the context's `ObservationRegistry` through its `@Bean` factory method. Inside the service, each valid invocation creates a new observation.

`LifecycleRecorder` is also a handler bean. Boot automatically registers `ObservationHandler` beans onto the registry; there is no manual registration line inside the service. The handler only accepts contexts named `stock.reserve` so other application observations do not skew the exercise's counters. [Source: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

In the lesson's default configuration, the Simple registry holds metrics in memory when no other registry is present. Therefore, you can fetch timers directly via the `MeterRegistry` bean without opening an HTTP endpoint or running Prometheus. [Source: Spring Boot — Simple](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#supported-monitoring-systems.simple).

The property `management.metrics.use-global-registry=false` keeps the example recording through the context's beans without binding to the static global registry. It does not disable the observed timers.

In a real application, nested classes can be split into separate files. The service can be registered with `@Service` and a constructor accepting `ObservationRegistry`; do not create a new Boot context per call. The lifecycle-counting handler is an explanatory tool for this lesson, not a mandatory part of every service.

## 7. When Manual Lifecycle Control Is Needed

For ordinary synchronous operations, using `observe(...)` reduces manual management. If there is a reason to hold the observation object directly, you must manage both the scope and the lifecycle completely.

The snippet below is an **alternative** to the `return Observation...observe(...)` part in the `reserve` method of the example class; keep the input validation before it and do not run both approaches around the same operation at once:

```java
Observation observation = Observation.createNotStarted(OBSERVATION_NAME, registry)
    .contextualName("reserve-stock")
    .lowCardinalityKeyValue("channel", channel.name().toLowerCase(Locale.ROOT))
    .highCardinalityKeyValue("sku", sku)
    .start();
try (Observation.Scope scope = observation.openScope()) {
    return reserveInternal(sku, quantity);
} catch (RuntimeException | Error error) {
    observation.error(error);
    throw error;
} finally {
    observation.stop();
}
```

`start()` does not replace `openScope()`. Closing the scope does not replace `stop()`. In the alternative snippet, `try` ensures context restoration, while `finally` ensures stopping the observation; the error branch still reports the error and rethrows the exception.

`observation.error(error)` signals an error to handlers rather than throwing an exception itself. The API also offers events (`Observation.Event`) to describe milestones occurring within an activity; add only useful milestones rather than turning them into a copy of every log line. [Source: Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

## 8. Interpreting Business Outcomes Correctly

### 8.1. Returning Normally Does Not Guarantee Acceptance

In the exercise, insufficient stock is modeled as an exception, so the timer receives an error tag. Another system might return `ReservationResult.REJECTED` as a normal return value. If the lambda returns normally, Observation does not know on its own that the enum or status code means failure.

When you need to distinguish acceptance/rejection without treating rejection as a technical error, you can design an `outcome` tag with a small set of values such as `accepted` and `rejected`. Whether to use exceptions or return values must follow the business contract; do not alter the contract just to make metrics convenient to view.

Do not put arbitrary error messages into low-cardinality tags. Two messages containing different order IDs can create a flood of new tag values even for the same error type.

### 8.2. Do Not Mask Exceptions Before the Observation Point

If code inside the lambda catches `OutOfStockException` and returns a fallback value, `observe(...)` no longer sees an exception escape. If you still need to reflect the failure on the observation, report it explicitly to the observation or represent an appropriate outcome.

Likewise, do not wrap an error in a new exception just to change a monitoring tag, or return a fake success after observing. Instrumentation should preserve the behavior and contract of the operation.

### 8.3. Retries, Transactions, and Async Tasks

With retries, an observation outside the whole retry loop represents one logical request; an observation per attempt represents individual execution attempts. If using both, give them distinct names and know which count you are reading.

With Spring declarative transactions, the transaction proxy wraps the method call. Consequently, an observation confined inside the method body may finish before the proxy completes the commit. If your question needs to include commit and commit-time errors, the boundary must surround the call through the appropriate proxy; do not assume "lambda returned" equals "transaction committed." [Source on proxy mechanism: Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).

For tasks returning `CompletableFuture`, a synchronous `observe(...)` wrapping only the call that returns the future typically measures only the creation/scheduling step. It does not wait for the work to finish. Switching threads or using a reactive pipeline also requires appropriate context propagation and lifecycle integration; do not keep a scope open on the calling thread and close it arbitrarily on another thread.

## 9. Checks When Data Is Missing

| Symptom | Check first |
| --- | --- |
| Code runs but there is no timer | Are you using Boot's registry bean, is there a metrics handler, is observation disabled, or is the meter filtered? |
| Operation name appears in many variants | Are SKU, order ID, or input data concatenated into the observation name? |
| Recording count exceeds expected business calls | Are you double-observing the same boundary, adding annotations over already-observed code, or counting individual retries? |
| Business error does not appear on the observation | Was the exception caught inside the lambda, or does business logic return a normal rejection status? |
| Current observation lingers after the call | If managed manually, was the scope closed and the previous state restored? |
| No trace despite having a timer | Are the appropriate tracer/handler/trace exporter present, and is the trace sampled? |
| Measurements do not appear over HTTP | The endpoint is a separate read path; first check whether the internal timer has data |

Do not wrap with an extra `@Observed` or add a second timer-creating handler just to fix an issue you do not yet understand. First verify that a single call enters the right boundary and the right registry. Observation components can be customized with conventions, predicates, or filters when a shared policy is needed; a simple operation does not have to define every kind of component.

## 10. Self-Check Exercises

1. Why did the program call `reserve` four times yet `observed.total` equals 3?
2. If you move the `quantity <= 0` check inside the lambda, how must you change your interpretation of the metrics?
3. If 1 item remains in stock and someone tries to reserve 2, why can a subsequent reservation still succeed?
4. Can SKU be used as a low-cardinality tag just because there is currently only one test product?
5. Why does the service hold `ObservationRegistry` in a field but not a shared Observation?
6. When returning a normal `REJECTED` result, does the API automatically report an error?
7. In the manual approach, what manages the scope and what guarantees stopping the observation?

Answers: (1) The quantity-0 input was rejected before the observation point. (2) That request enters the observed set with an input error; both the total count and the denominator definition change. (3) The insufficient-stock branch checks and throws an exception before updating stock. (4) Do not extrapolate from test data to the long-term value set; design according to the real number of values that can arise. (5) The registry is shared configuration, while an Observation is per-invocation state. (6) No; you must classify the outcome or report an error per the chosen contract. (7) Try-with-resources closes the scope; `finally` calls `stop()`; the catch block reports the error and rethrows.
