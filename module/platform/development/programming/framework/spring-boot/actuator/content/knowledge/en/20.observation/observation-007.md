# Filtering or Enriching Data with ObservationPredicate and ObservationFilter

## 1. Two Different Questions: Whether to Observe and What Else to Record?

An application may create observations for report rendering, HTTP calls, or background tasks. As observation points grow, you need shared policies: skip certain internal checks, exclude synthetic probe runs from business statistics, or attach deployment region and processing outcome to observation data.

Micrometer provides two mechanisms with distinct roles:

- `ObservationPredicate`: decides whether an observation is enabled.
- `ObservationFilter`: modifies `Observation.Context` before notifying handlers (`ObservationHandler`) on completion.

The name `Filter` easily leads learners to think it drops entire observations. Here, the keep/drop decision belongs to the predicate; the filter transforms or enriches the context of an already-accepted observation. [Source: Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

`Observation.Context` carries data for one observation run for handlers to use; scope is the boundary that sets the current active observation context.

This lesson is set in Spring Boot 3.3.x, using a runnable example with Spring Boot 3.3.0 and Micrometer 1.13.0. The goal is to understand the exact execution timing so filtering policies do not distort data or unintentionally affect business logic.

## 2. Where Predicate and Filter Sit in the Lifecycle

With the observation creation pattern used in this lesson:

```text
Prepare context with input data
    → call createNotStarted(name, contextSupplier, registry)
    → evaluate ObservationPredicates
        → any predicate returns false: use no-op observation
        → all return true: active observation
    → start and onStart handlers
    → run task in scope; may report errors/events
    → on stop: apply ObservationFilters
    → onStop handlers receive filtered context
```

A no-op observation still lets the task inside `observe(...)` run. It is not an `if` statement that blocks functionality. Therefore, a predicate does not replace access control, input validation, or business feature toggles.

In Micrometer 1.13.0, the overload `createNotStarted(name, contextSupplier, registry)` obtains the context, evaluates predicates, and returns a no-op observation if the condition fails. This happens right inside the creation call, before chained tagging calls that follow. [Source: Observation.java 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/Observation.java).

At the stop step, `SimpleObservation` applies filters sequentially and then passes the resulting context to `onStop`. [Source: SimpleObservation.java 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/SimpleObservation.java).

| Aspect | ObservationPredicate | ObservationFilter |
| --- | --- | --- |
| Data received | Name and context at evaluation time | Context at stop time |
| Return type | `boolean` | `Observation.Context` |
| Purpose | Enable or skip recording the observation | Add, normalize, or remove data keys in context |
| Knows the task's final error? | Cannot know an error that has not happened yet | Can read the error reported onto the context |
| Prevents business code from running? | No | No |
| Replaces metrics/trace export policies? | No | No |

## 3. ObservationPredicate: Deciding Before Starting

### 3.1. Read the Name from the Parameter and Check the Context Type

`ObservationPredicate` has the check signature `test(String name, Observation.Context context)`. In Micrometer 1.13, it extends `BiPredicate<String, Observation.Context>`, so it can be written as a lambda. [Source: ObservationPredicate 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/ObservationPredicate.java).

A name-based rule can skip observations with the prefix `internal.`. For policies based on business data, use a typed context subclass and check its type before accessing fields.

In the example, `RenderContext` has a `synthetic` flag indicating a run created to probe the system. The predicate skips recording synthetic runs without preventing them from producing results. If the context is of another type, this predicate lets it pass; it has no basis to assume every other activity should be excluded.

Use the `name` parameter to inspect the name in a predicate. Do not assume all context attributes are already populated as they are at the `onStop` stage.

### 3.2. Data Must Exist Before the Predicate Runs

Consider the call chain:

```text
createNotStarted(...) → lowCardinalityKeyValue(...) → observe(...)
```

The predicate was already evaluated in the first step, so it cannot read a tag added only in the second step to decide about that same creation. Nor can it wait for a filter to add data and go back to decide whether to start the observation.

The proper design in this lesson is preparing the `synthetic` flag inside `RenderContext` before passing the context to `createNotStarted`. Fields known upfront serve early decisions; summary tags can be attached separately at the appropriate time.

If a framework context already carries data at creation time, a predicate can use that data. What to check is **when the data exists**, not a blanket rule that predicates may never read tags.

Do not use `context.getError() != null` to try to "observe only runs that will fail later." The error has not occurred yet at early decision time. You can observe and then classify outcomes at stop time; trace sampling based on completed data is a separate concern.

### 3.3. Multiple Predicates Combine with AND

An observation is enabled only when all registered predicates return `true`. Encountering `false` can short-circuit evaluation. [Source: ObservationRegistry.ObservationConfig 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/ObservationRegistry.java).

| Name rule | Synthetic rule | Observation recorded? |
| --- | --- | --- |
| Pass | Pass | Yes |
| Block | Pass | No |
| Pass | Block | No |
| Block | Block | No |

Two predicate beans do not form an OR choice. If a policy needs condition A **or** B, express the OR inside that single predicate; remaining predicates stay mandatory conditions.

Do not put business side effects inside predicates or depend on every predicate being invoked. Predicates should be fast, clear, and read-only on needed data.

## 4. ObservationFilter: Enriching Data Before onStop

### 4.1. Modify the Context and Return It

`ObservationFilter` has the method `Observation.Context map(Observation.Context context)`. Its contract is to adjust the context and return the resulting context. [Source: ObservationFilter 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-observation/src/main/java/io/micrometer/observation/ObservationFilter.java).

In the example, the filter handles only `RenderContext` for the `report.render` activity, then adds:

| Key | Kind | Value in lesson |
| --- | --- | --- |
| `region` | Low cardinality | `vn-south` |
| `result` | Low cardinality | `completed` or `failed` |
| `request.id` | High cardinality | Request ID of each run |

The filter can read `context.getError()` to classify errors already reported on the observation. `completed` in this lesson only means no error was reported, not confirmation that every transaction or external task succeeded.

For out-of-scope contexts, return the context unchanged. For contexts to process, normally modify the existing object and return it. Do not return `null` to skip an observation and do not arbitrarily replace it with `new Observation.Context()`: handlers may already have stored state such as timing samples in the original context.

If there are multiple filters, the result of the previous filter is passed to the next. Two filters modifying the same key can make the outcome depend on registration order. Separate responsibilities clearly so one filter does not have to guess whether another has run; if order is needed, declare and verify it in the integration setup.

### 4.2. Filters Run Late and Cannot Rewrite the Past

A tag added before `onStop` can appear on a timer finalized at `onStop`. It does not retroactively add itself to data a handler created at `onStart`, or to events/logs already processed earlier.

With `DefaultMeterObservationHandler` 1.13, a long-task timer can be created right at start time, while the activity's summary timer is recorded at stop time. Tags added after start are not automatically backfilled onto that long-task timer. [Source: DefaultMeterObservationHandler 1.13.0](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java).

Therefore, if `region` must appear on active measurements as well, set it before starting or use an appropriate observation convention. The exercise intentionally adds `region` via a filter to expose this timing boundary.

Similarly, removing a key in a final filter does not guarantee sensitive data was never read earlier by another handler. Do not put unnecessary data into the context upfront and rely solely on a late filter to retract it.

### 4.3. Keep Tag Value Counts Bounded

Low cardinality has a small, controlled value set. `result` has only two values in the lesson; `request.id` varies per request so it uses high cardinality. In the default pipeline, low-cardinality tags go to metrics and traces, while high-cardinality tags do not become metric tags. [Source: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

A filter does not turn a request ID into low-cardinality data. Do not put IDs or arbitrary error messages into metric tags just because enrichment happens in one centralized spot.

## 5. Registering in Spring Boot

In an application with Actuator and observation configuration, declare `ObservationPredicate` and `ObservationFilter` beans. Boot automatically registers those beans on the application-managed `ObservationRegistry`. There is no need to create another registry inside a service. [Source: Spring Boot — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

The complete example below uses:

- Two predicate beans: skip internal names and skip synthetic data.
- One filter bean: enrich descriptive metadata for observed reports.
- One verification handler: records data seen at start and stop.
- One service using the constructor-injected registry.

If using plain Micrometer outside Boot, register via `registry.observationConfig().observationPredicate(...)` and `.observationFilter(...)`, and configure the required handlers. Do not both register manually and let Boot register the same policy without checking duplicate effects.

For simple name-based rules, Boot also provides configuration such as:

```properties
management.observations.enable.internal=false
```

For the name `internal.report.check` in this lesson, that property can express skipping recording without a Java name predicate. That is an alternative configuration option for the corresponding policy, not a mandatory extra step to add to the example. Another predicate returning `true` cannot re-enable an observation already blocked by another policy.

## 6. Hands-On: Skip Recording Two Runs While Running All Four Tasks

### 6.1. Scenario

The program creates a simple text representation for reports. This is an experiment in observation policy, not a PDF exporter or full report-storage system.

| Run | Name | Synthetic | Business outcome | Observed? |
| --- | --- | --- | --- | --- |
| R-1 | `report.render` | `false` | Returns normal text | Yes |
| R-2 | `report.render` | `true` | Still returns probe text | No |
| R-3 | `internal.report.check` | `false` | Still returns internal check result | No |
| R-4 | `report.render` | `false` | Blank body, throws error | Yes |

The filter runs for the two accepted observations. It adds the outcome tag after knowing whether the branch succeeded or failed. The verification audit also shows `region` is absent at start yet present at stop.

### 6.2. File pom.xml

JDK 17 or newer and Maven are required. Create a dedicated practice directory and place `pom.xml` and `ObservationPolicyApplication.java` side by side. The first dependency download requires network access.

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
  <artifactId>observation-policy-demo</artifactId>
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

The parent pins a compatible version set. No external registry library is needed for an experiment holding metrics in memory.

### 6.3. File ObservationPolicyApplication.java

```java
package example.policy;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.common.KeyValue;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationPredicate;
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
public class ObservationPolicyApplication {
    static final String REPORT = "report.render";

    static final class RenderContext extends Observation.Context {
        final String requestId;
        final boolean synthetic;

        RenderContext(String requestId, boolean synthetic) {
            this.requestId = requestId;
            this.synthetic = synthetic;
        }
    }

    static final class ReportService {
        private final ObservationRegistry registry;
        final AtomicInteger businessRuns = new AtomicInteger();

        ReportService(ObservationRegistry registry) {
            this.registry = registry;
        }

        String render(String requestId, boolean synthetic, String body) {
            return execute(REPORT, requestId, synthetic, body);
        }

        String internalCheck(String requestId) {
            return execute("internal.report.check", requestId, false, "check");
        }

        private String execute(String name, String requestId, boolean synthetic, String body) {
            RenderContext context = new RenderContext(requestId, synthetic);
            return Observation.createNotStarted(name, () -> context, registry)
                .lowCardinalityKeyValue("format", "text")
                .observe(() -> {
                    businessRuns.incrementAndGet();
                    if (body.isBlank()) {
                        throw new IllegalArgumentException("Empty report");
                    }
                    return requestId + "|" + body.strip();
                });
        }
    }

    static final class ReportMetadataFilter implements ObservationFilter {
        final AtomicInteger calls = new AtomicInteger();

        @Override
        public Observation.Context map(Observation.Context context) {
            if (!(context instanceof RenderContext render) || !REPORT.equals(context.getName())) {
                return context;
            }
            calls.incrementAndGet();
            context.addLowCardinalityKeyValue(KeyValue.of("region", "vn-south"));
            context.addLowCardinalityKeyValue(KeyValue.of("result",
                context.getError() == null ? "completed" : "failed"));
            context.addHighCardinalityKeyValue(KeyValue.of("request.id", render.requestId));
            return context;
        }
    }

    static final class LifecycleAudit implements ObservationHandler<Observation.Context> {
        final List<String> startRegions = new CopyOnWriteArrayList<>();
        final List<String> stopRegions = new CopyOnWriteArrayList<>();
        final List<String> stopRequestIds = new CopyOnWriteArrayList<>();

        private static String value(KeyValue keyValue) {
            return keyValue == null ? "missing" : keyValue.getValue();
        }

        @Override
        public boolean supportsContext(Observation.Context context) {
            return context instanceof RenderContext && REPORT.equals(context.getName());
        }

        @Override
        public void onStart(Observation.Context context) {
            startRegions.add(value(context.getLowCardinalityKeyValue("region")));
        }

        @Override
        public void onStop(Observation.Context context) {
            stopRegions.add(value(context.getLowCardinalityKeyValue("region")));
            stopRequestIds.add(value(context.getHighCardinalityKeyValue("request.id")));
        }
    }

    @Bean
    ObservationPredicate skipInternalObservations() {
        return (name, context) -> !name.startsWith("internal.");
    }

    @Bean
    ObservationPredicate skipSyntheticReports() {
        return (name, context) ->
            !(context instanceof RenderContext render && render.synthetic);
    }

    @Bean
    ReportMetadataFilter reportMetadataFilter() {
        return new ReportMetadataFilter();
    }

    @Bean
    LifecycleAudit lifecycleAudit() {
        return new LifecycleAudit();
    }

    @Bean
    ReportService reportService(ObservationRegistry registry) {
        return new ReportService(registry);
    }

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(ObservationPolicyApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);
        application.setDefaultProperties(Map.of(
            "logging.level.root", "OFF",
            "management.metrics.use-global-registry", "false",
            "management.observations.long-task-timer.enabled", "true"));

        try (ConfigurableApplicationContext context = application.run(args)) {
            ReportService service = context.getBean(ReportService.class);
            MeterRegistry meters = context.getBean(MeterRegistry.class);
            ObservationRegistry observations = context.getBean(ObservationRegistry.class);
            ReportMetadataFilter filter = context.getBean(ReportMetadataFilter.class);
            LifecycleAudit audit = context.getBean(LifecycleAudit.class);

            System.out.println("normal.result=" + service.render("R-1", false, "Revenue"));
            System.out.println("synthetic.result=" + service.render("R-2", true, "Probe"));
            System.out.println("internal.result=" + service.internalCheck("R-3"));
            try {
                service.render("R-4", false, " ");
            } catch (IllegalArgumentException error) {
                System.out.println("failed=" + error.getClass().getSimpleName());
            }

            System.out.println("business.runs=" + service.businessRuns.get());
            System.out.println("timer.completed="
                + meters.get(REPORT).tag("result", "completed").timer().count());
            System.out.println("timer.failed="
                + meters.get(REPORT).tag("result", "failed").timer().count());
            System.out.println("filter.calls=" + filter.calls.get());
            System.out.println("start.region=" + audit.startRegions);
            System.out.println("stop.region=" + audit.stopRegions);
            System.out.println("stop.requestIds=" + audit.stopRequestIds);
            boolean requestIdIsTag = meters.find(REPORT).timers().stream()
                .anyMatch(timer -> timer.getId().getTag("request.id") != null);
            System.out.println("timer.hasRequestId=" + requestIdIsTag);
            System.out.println("active.hasRegion="
                + (meters.get(REPORT + ".active").longTaskTimer().getId().getTag("region") != null));
            System.out.println("current.cleared=" + (observations.getCurrentObservation() == null));
        }
    }
}
```

### 6.4. Compiling and Running

In PowerShell, in the directory containing the two files:

```powershell
mvn dependency:copy-dependencies -DincludeScope=runtime
New-Item -ItemType Directory -Force -Path target/classes | Out-Null
javac --release 17 -encoding UTF-8 -cp "target/dependency/*" -d target/classes ObservationPolicyApplication.java
java -cp "target/classes;target/dependency/*" example.policy.ObservationPolicyApplication
```

On Linux/macOS, create the directory with `mkdir -p target/classes` and replace the `;` classpath separator in `java` with `:`. The package is `example.policy`; when compiling directly from the file, `-d` creates the package tree in the target directory. In a standard Maven project, place the file at `src/main/java/example/policy/`.

The application opens no web server and calls no external monitoring system. It disables the banner and startup logs so stdout is easy to compare; that setting is solely for the exercise.

Running as-is yields stdout:

```text
normal.result=R-1|Revenue
synthetic.result=R-2|Probe
internal.result=R-3|check
failed=IllegalArgumentException
business.runs=4
timer.completed=1
timer.failed=1
filter.calls=2
start.region=[missing, missing]
stop.region=[vn-south, vn-south]
stop.requestIds=[R-1, R-4]
timer.hasRequestId=false
active.hasRegion=false
current.cleared=true
```

### 6.5. Reading the Evidence

1. The first three output lines and the `failed` line show business logic still ran on all four calls, including R-2 and R-3 which were excluded from observation.
2. `business.runs=4` confirms total executions inside the lambda. Predicates did not block those tasks.
3. `timer.completed=1` and `timer.failed=1` belong only to the two observations that passed both predicates.
4. `filter.calls=2` shows the filter did not run for the two blocked no-op observations.
5. `start.region=[missing, missing]` and `stop.region=[vn-south, vn-south]` verify the filter enriches data at the stop phase.
6. `stop.requestIds=[R-1, R-4]` shows high-cardinality data is available when the handler receives `onStop` for the two valid observations.
7. `timer.hasRequestId=false` confirms the request ID was not added as a default timer tag.
8. `active.hasRegion=false` proves tags added late do not automatically appear on a previously created long-task timer.
9. `current.cleared=true` confirms after all runs there is no lingering current observation on the example's thread.

The program explicitly enables `management.observations.long-task-timer.enabled=true` to make `.active` measurements visible. That does not cause the filter to run earlier. Counters and lists in the filter/handler are verification data for the lesson, not a requirement to retain all observations' history in memory in a real application.

The example installs no tracer, so it does not claim spans were exported to a trace store. It checks policies at the Observation level and the metrics generated from them.

## 7. Boundaries to Respect When Applying

### 7.1. Predicates Apply Per Observation

Blocking one name or context does not mean every child observation, direct `MeterRegistry` measurement, or task log is blocked. Each observation point has its own evaluation; independent logs or metric calls still follow their own execution paths.

When writing a global predicate, always scope by name or context type. A `return false` branch for all unrecognized contexts can accidentally drop framework telemetry you did not intend to touch.

### 7.2. Filters Are Not an Error-Isolation Layer

Filters sit inside the observation completion path. In the implementation used here, the filter chain is invoked before `onStop` notifications; do not assume throwing an error in a filter is silently ignored. Errors from an observation policy can fail the call or mask the original error.

Keep filters fast; do not call network services just to look up tags at the end of every task. For stable environment data, read existing configuration; for business data, put required fields into the context along the proper lifecycle. Return a valid context and preserve state used by handlers.

### 7.3. Adding and Removing Keys Must Have a Clear Purpose

`Observation.Context` can add or remove keys, such as `removeLowCardinalityKeyValue(...)`. However, modifying at the end only affects data read afterward; it does not retract a meter or event already created earlier.

Likewise, do not change the observation name at the end expecting all handlers that started with the old name to be uniformly updated. If the goal is naming/tagging conventions for a kind of operation, consider `ObservationConvention` and when the data needs to exist.

If multiple policies use the same key, define clearly who owns that key and which value takes precedence. Do not rely on class name ordering or source file location.

## 8. Choosing the Right Mechanism for Each Need

| Need | Mechanism to consider |
| --- | --- |
| Skip recording the entire observation point for certain names/contexts | `ObservationPredicate` or Boot's Observation enable/disable config |
| Enrich descriptive data when the activity stops | `ObservationFilter` |
| Name and tag according to an operation's convention | `ObservationConvention` |
| Need data available right when handlers start | Prepare context/tags before starting or use an appropriate convention |
| Filter only specific metric meters | `MeterRegistry`-level policy, such as `MeterFilter` |
| Adjust trace sampling | Tracing sampling configuration |
| Toggle business features or check permissions | Corresponding business logic/mechanisms |

Calling them "filtering" does not mean these mechanisms replace one another. An `ObservationPredicate` can exclude both metrics and tracing produced by that observation point, whereas a `MeterFilter` acts only on the metrics path.

## 9. Diagnosing Common Misconceptions

| Symptom | Where to check |
| --- | --- |
| Predicate does not see a tag chained right after createNotStarted | That tag was added after the predicate ran; prepare decision data in the context beforehand |
| Wanted to keep only errors yet see no observations | Using a not-yet-occurred outcome as an early condition, such as checking `getError` in a predicate |
| Two predicates thought to be OR yet data is dropped | Predicates are combined with AND |
| Filter adds a tag yet `onStart` still does not see it | Filters run before `onStop`, not before `onStart` |
| Timer has `region` yet active measurement lacks it | The two meters read metadata at two different milestones |
| Filter bean exists yet service is unaffected | Service may be using a self-created registry instead of Boot's registry bean, or the observation was blocked by a predicate |
| No data after filter returns null/empty context | A filter is not how to drop observations; return a valid context and preserve needed state |
| Excluded observation yet task still runs | This is intended behavior: predicates control recording, not business execution |

In real checks, inspect all four things: task execution count, accepted observation count, data seen by handlers at start, and data seen at stop. Looking only at an empty chart will not distinguish registry wiring errors, predicate blocking, or broken export paths.

## 10. Self-Check

1. Why does R-2 still produce a result even though the synthetic predicate returns false?
2. If a name predicate passes yet a context predicate blocks, what is the combined result?
3. Is a tag added via `lowCardinalityKeyValue` right after `createNotStarted` guaranteed to exist when that creation call's predicate runs?
4. Why can the filter classify `result` by error in the example, while a predicate cannot use a future error to select an observation?
5. If `region` is needed on both the completed timer and the long-task timer, is adding `region` only in a late filter enough?
6. Why should you not return `null` or an empty Context to "filter out" data?
7. What must two filters writing the same key watch out for?

Answers: (1) No-op skips observation recording, not lambda execution. (2) Blocked because the combined condition is AND. (3) No; with the overload in the lesson, predicates run before chained tagging calls. (4) Filters run at completion when errors have already been reported; predicates decide early. (5) Not enough; the data must exist when the active measurement is created. (6) It can lose handler state or cause errors; predicates are where non-recording is decided. (7) Scope, key ownership, and application order must be clear and verified.
