# Avoiding Unnecessary Nested Observations When the Framework Already Observes

## 1. Problem: Adding Measurement Points Without Adding Information

When wanting to know whether an API runs fast or slow, it is tempting to wrap the entire controller in a self-created observation. However, in a Spring Boot application with Spring MVC observation active, the HTTP request already has an observation at the framework layer.

If the new observation merely wraps nearly the exact same processing, we add another observation lifecycle without gaining a new answer about the system. Traces may become longer, meter counts increase, and readers struggle to tell how the two measurements differ.

Example of an already-observed request:

~~~text
http.server.requests
└── controller processing and returning response
~~~

After wrapping the controller a second time:

~~~text
http.server.requests
└── app.controller
    └── still the same controller processing
~~~

The `app.controller` observation here is questionable because its goal is still "measure the whole API." Conversely, a child observation measuring only the pricing step can answer a distinct question: "Out of the API processing time, how much does pricing take?".

This lesson's goal is knowing **when to reuse an existing observation, when to enrich information, and when to create a meaningful child observation**. Having the fewest observations is not the sole criterion; each observation boundary must have a clear purpose.

Before adding your own instrumentation code, Micrometer recommends checking whether the component in use already has built-in instrumentation. [Micrometer: Instrumentation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

## 2. What Does the Framework Already Observe?

### 2.1. Spring MVC HTTP Observation

With Spring Boot 3.3 and suitable configuration conditions, Spring MVC auto-configuration observes requests handled by controllers and functional handlers. The default name is `http.server.requests`. [Spring Boot 3.3: Spring MVC Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

In the Servlet stack, `ServerHttpObservationFilter` participates in the request lifecycle. The HTTP observation wraps the processing chain downstream of the filter, including Spring MVC handling. It is not identical to the duration of a single Java method in the controller alone.

Spring Boot has `WebMvcObservationAutoConfiguration` to register the corresponding filter when a Servlet application, required classes, and the `ObservationRegistry` bean are present. Therefore, check actual configuration rather than assuming merely having a controller guarantees observation data exists. [WebMvcObservationAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/observation/web/servlet/WebMvcObservationAutoConfiguration.html).

### 2.2. Built-in Boundaries to Understand Before Wrapping Further

| Component under review | What to check before instrumenting yourself |
| --- | --- |
| Spring MVC controller | Is the framework's HTTP observation active? |
| Outbound HTTP call | Is the HTTP client configured with the registry and observation support? |
| Method with `@Observed` | Is the annotation's aspect active and does the call go through a proxy? |
| Data-access or messaging library | Do the current version and configuration provide instrumentation for this operation? |
| Task outside an HTTP request | Is there already an observation boundary from a scheduler, listener, or outer caller? |

This table lists verification questions, not a claim that every library is automatically observed by Spring Boot under every configuration. Check the exact version and how components are constructed.

Annotations must also be distinguished. `@Observed`, when processed, can create an observation; `@Timed` can add timing measurements at the metric layer. Do not attribute all duplicate data to a single mechanism.

## 3. Valid Nested Observations vs. Redundant Nested Observations

A **nested observation** is an observation created while another observation is already the current observation in the execution scope. The inner observation can link to the parent observation.

The parent–child relationship describes processing structure; it does not by itself prove adding an observation is right or wrong.

### 3.1. Three Criteria to Decide

Before adding an observation, determine:

1. **Unit of work:** Does it represent an HTTP request, a service call, or a specific business step?
2. **Time boundary:** How do its start and end differ from what is already measured?
3. **Diagnostic question:** If removed, what essential information would be lost?

If all three answers nearly overlap with an existing observation, prefer using existing data or enriching metadata.

| Situation | Assessment | Action to take |
| --- | --- | --- |
| Wrapping the entire controller just to know how long the API takes | Usually duplicates the HTTP server observation's goal | Use the HTTP observation |
| Adding `@Observed` to a controller already observed by the framework, with no distinct purpose | Risks creating a redundant observation | Remove the extra instrumentation or redesign the boundary |
| Adding a "business operation type" tag to an HTTP request | Needs more information, not necessarily another lifecycle | Enrich the existing observation/context |
| Measuring the pricing step inside a checkout flow | Can answer a distinct question | Create a business observation at that step |
| An HTTP client call inside an HTTP server request | Two different operations | Keep the parent–child relationship when properly configured |
| Wrapping every formatter, getter, and tiny calculation | Easily adds noise with little value | Pick steps that genuinely need diagnosis |

Spring Boot warns that applying observation annotations to classes/methods already measured by the framework can create duplicate observation data. Choose the mechanism that owns the instrumentation point according to the application's goal. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

### 3.2. Cost and Meaning of Data

Redundant observations can increase handler invocations, meters, or spans when the corresponding components are installed. The exact increase depends on actual configuration; there is no rule that every observation always exports a span externally.

Another consequence is **misinterpretation**:

- Two differently named timers may both measure most of the same request's duration.
- Summing recording counts across all timers does not equal the HTTP request count.
- Parent duration usually already includes child duration; summing both double-counts the overlapping interval.
- Renaming a controller-wrapping observation makes its name differ from the HTTP observation, without creating new business meaning on its own.

Hypothetical example: an HTTP request takes 25 ms, of which the pricing step takes 15 ms. You must not deduce total processing is 40 ms by adding the two measurements. Nor should you subtract p95 percentiles of two timers to compute a "remaining time p95."

## 4. Enriching Information on an Existing Observation

### 4.1. Use the Current Observation When Targeting the Exact Active Scope

The following snippet illustrates adding a tag in code that already has an injected `ObservationRegistry`:

~~~java
Observation current = registry.getCurrentObservation();
if (current != null) {
    current.lowCardinalityKeyValue("business.operation", "checkout.preview");
}
~~~

This is a snippet integrated into an existing method, not a standalone program.

It creates no new observation. However, `current` is the innermost active observation: if already inside a child observation of a library or business step, the tag will be attached to that observation. Therefore, make sure you are targeting the intended object.

Do not call `start()`, `stop()`, or terminate the scope of a framework-owned observation yourself. The framework is responsible for closing its lifecycle. Application code only adds data when needed.

### 4.2. Targeting the HTTP Request Context Specifically in Spring MVC

When handling a Servlet request and wanting to enrich the HTTP observation itself, you can look up the context via the request:

~~~java
ServerHttpObservationFilter.findObservationContext(request)
        .ifPresent(context -> context.addLowCardinalityKeyValue(
                KeyValue.of("business.operation", "checkout.preview")));
~~~

Required types:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import io.micrometer.common.KeyValue;
import org.springframework.web.filter.ServerHttpObservationFilter;
~~~

The API returns an `Optional` because the context may not exist. Do not treat failing to find the context as a reason to automatically create a replacement HTTP observation right inside the controller.

Spring Framework provides the request context and extension points such as `ServerRequestObservationConvention` to contribute metadata to HTTP observations. [Spring Framework: Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html).

### 4.3. Choosing the Right Extension Point

| Scope of enrichment | Approach |
| --- | --- |
| One tag on the request currently being handled | Add to the existing request context |
| Uniform HTTP tagging rules across the application | Customize `ServerRequestObservationConvention` |
| Enrich/process context at the end of an observation | Consider `ObservationFilter` with proper context-type checks |
| Measure a business step with its own boundary | Create a new observation at that step |

If extending the default convention and wanting to keep default tags, preserve the data from the base convention. Replacing the whole convention can drop information such as method, status, or URI template if not fully reimplemented.

The `business.operation` tag should have a bounded value set, such as `checkout.preview` or `checkout.submit`. Do not use order IDs or full URLs containing identifiers as low-cardinality tags.

### 4.4. Current Observation Is Not a Blanket Suppression Mechanism

Do not apply a rule "if there is a current observation, skip every new observation." A request with an HTTP observation can still need a child observation for a pricing step or an outbound call.

Conversely, `getCurrentObservation() == null` can result from having no active scope, observation being disabled, using the wrong registry, or losing context when switching threads. Creating a new root observation can mask a context-propagation bug rather than solving it.

Micrometer separates creating observations from propagating context; parent–child relationships must be preserved across the right execution scopes. [Micrometer: Instrumentation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

## 5. Hands-On: Observing Three Ways to Handle One Request

### 5.1. Objective and Scope of the Experiment

The program uses Spring MVC **6.1.8** and Micrometer **1.13.0**, matching the versions managed by Spring Boot **3.3.0**. The code compiles with `--release 17` and was run on JDK 21.

The three endpoints in the experiment have distinct purposes:

- `/duplicate` creates an extra observation wrapping controller handling.
- `/enrich` only adds a tag to the HTTP observation.
- `/business` creates a child observation for the pricing calculation step.

We use `MockMvc` to dispatch requests through Spring MVC's processing mechanism without opening a network port. It uses `DispatcherServlet` and mock Servlet objects rather than merely invoking controller methods directly. [Spring Framework: MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html).

**In this standalone experiment, we explicitly register one `ServerHttpObservationFilter` on MockMvc.** Spring's real filter creates the HTTP observation for each request. This sets up the verification environment; in a real auto-configured Spring Boot application, do not copy this filter registration to add a second observation filter.

MockMvc lets you register filters in the request chain via `addFilters(...)`. [Spring Framework: Filter Registrations](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/filters.html).

### 5.2. Dependency File

Create the structure:

~~~text
observation-boundary-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ObservationBoundaryLab.java
~~~

Contents of `pom.xml`:

~~~xml
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
    <artifactId>observation-boundary-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
        </dependency>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

The parent is used to manage library versions. This program does not boot a Spring Boot application via `SpringApplication`; the registry and filter are built explicitly in the lab environment.

`spring-test` is on the program's classpath because `main` itself uses MockMvc. In a typical application project, test libraries belong in the appropriate test scope.

### 5.3. Complete Program

Contents of `src/main/java/example/ObservationBoundaryLab.java`:

~~~java
package example;

import java.util.ArrayList;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

import jakarta.servlet.http.HttpServletRequest;
import io.micrometer.common.KeyValue;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.ServerHttpObservationFilter;

public class ObservationBoundaryLab {
    public static void main(String[] args) throws Exception {
        Logger.getLogger("").setLevel(Level.OFF);
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        try {
            ObservationRegistry registry = ObservationRegistry.create();
            Recorder recorder = new Recorder();
            registry.observationConfig()
                    .observationHandler(new DefaultMeterObservationHandler(meters))
                    .observationHandler(recorder);
            PricingService pricing = new PricingService(registry);
            MockMvc mvc = MockMvcBuilders
                    .standaloneSetup(new CheckoutController(registry, pricing))
                    .addFilters(new ServerHttpObservationFilter(registry))
                    .build();
            for (String path : List.of("/duplicate", "/enrich", "/business")) {
                MvcResult result = mvc.perform(MockMvcRequestBuilders.get(path)).andReturn();
                List<Stopped> events = recorder.drain();
                System.out.println("REQUEST " + path + " status="
                        + result.getResponse().getStatus() + " body="
                        + result.getResponse().getContentAsString());
                for (Stopped event : events) {
                    System.out.println("STOP " + event.name() + " parent="
                            + event.parent() + " operation=" + event.operation());
                }
                Timer timer = meters.find("http.server.requests").tag("uri", path).timer();
                System.out.println("OBSERVATIONS " + path + "=" + events.size());
                System.out.println("SERVER_TIMER " + path + "="
                        + (timer == null ? 0 : timer.count()));
            }
            long requests = meters.find("http.server.requests").timers().stream()
                    .mapToLong(Timer::count).sum();
            System.out.println("TOTAL_SERVER_REQUESTS=" + requests);
        } finally {
            meters.close();
        }
    }

    record Stopped(String name, String parent, String operation) { }

    static class Recorder implements ObservationHandler<Observation.Context> {
        private final List<Stopped> stopped = new ArrayList<>();

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStop(Observation.Context context) {
            String parent = context.getParentObservation() == null ? "none"
                    : context.getParentObservation().getContextView().getName();
            KeyValue operation = context.getLowCardinalityKeyValue("business.operation");
            stopped.add(new Stopped(context.getName(), parent,
                    operation == null ? "none" : operation.getValue()));
        }

        List<Stopped> drain() {
            List<Stopped> events = new ArrayList<>(stopped);
            stopped.clear();
            return events;
        }
    }

    static class PricingService {
        private final ObservationRegistry registry;

        PricingService(ObservationRegistry registry) {
            this.registry = registry;
        }

        int calculate() {
            return Observation.createNotStarted("demo.price.calculate", registry)
                    .observe(() -> 2 * 50 + 20);
        }
    }

    @RestController
    static class CheckoutController {
        private final ObservationRegistry registry;
        private final PricingService pricing;

        CheckoutController(ObservationRegistry registry, PricingService pricing) {
            this.registry = registry;
            this.pricing = pricing;
        }

        @GetMapping("/duplicate")
        String duplicate() {
            return Observation.createNotStarted("demo.controller", registry)
                    .observe(() -> "120");
        }

        @GetMapping("/enrich")
        String enrich(HttpServletRequest request) {
            ServerHttpObservationFilter.findObservationContext(request)
                    .ifPresent(context -> context.addLowCardinalityKeyValue(
                            KeyValue.of("business.operation", "checkout.preview")));
            return "120";
        }

        @GetMapping("/business")
        String business() {
            return Integer.toString(pricing.calculate());
        }
    }
}
~~~

In the code:

- `DefaultMeterObservationHandler` records timers into the in-memory registry.
- `Recorder` records `onStop` events to inspect name, parent observation, and business tag.
- Filter, controller, and service all share one `ObservationRegistry`.
- MockMvc requests run synchronously and sequentially; hence `Recorder` uses `ArrayList` in this lab.
- `PricingService.calculate()` is an independent step with its own name. The small arithmetic simply makes the example runnable; in a real system, only add an instrumentation point if there is a need to analyze that step.

`Recorder` is not a collector for an environment serving multiple concurrent requests. Do not copy this simple list-storing structure as a monitoring mechanism for production runtime.

### 5.4. Compiling and Running

With Maven and JDK 17 or newer, run in the directory containing `pom.xml`. Example PowerShell/Windows commands:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/main/java/example/ObservationBoundaryLab.java
java -cp "out;lib/*" example.ObservationBoundaryLab
~~~

On Linux/macOS:

~~~shell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
mkdir -p out
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/main/java/example/ObservationBoundaryLab.java
java -cp "out:lib/*" example.ObservationBoundaryLab
~~~

The first run requires downloading dependencies if not already cached locally. The program needs no external monitoring system. It exits after three requests and closes `SimpleMeterRegistry` in `finally`.

### 5.5. Stdout

~~~text
REQUEST /duplicate status=200 body=120
STOP demo.controller parent=http.server.requests operation=none
STOP http.server.requests parent=none operation=none
OBSERVATIONS /duplicate=2
SERVER_TIMER /duplicate=1
REQUEST /enrich status=200 body=120
STOP http.server.requests parent=none operation=checkout.preview
OBSERVATIONS /enrich=1
SERVER_TIMER /enrich=1
REQUEST /business status=200 body=120
STOP demo.price.calculate parent=http.server.requests operation=none
STOP http.server.requests parent=none operation=none
OBSERVATIONS /business=2
SERVER_TIMER /business=1
TOTAL_SERVER_REQUESTS=3
~~~

## 6. Reading the Evidence and Making Decisions

### 6.1. `/duplicate`: Extra Lifecycle Without a Distinct Purpose

~~~text
http.server.requests
└── demo.controller
~~~

`demo.controller` is created inside the HTTP scope, so it gets `http.server.requests` as its parent. The child observation stops before the parent observation, matching the `STOP` lines.

The endpoint merely returns `"120"` and does not measure a distinct business step. If the goal is simply tracking this whole API, the HTTP observation already provides the appropriate boundary.

`OBSERVATIONS /duplicate=2` counts two observation lifecycles in the experiment. `SERVER_TIMER /duplicate=1` shows the HTTP timer recorded exactly one request. **Two differently named observations do not mean the `http.server.requests` timer was incremented twice.**

The issue here is a low-value extra measurement point and the risk of users mis-aggregating data, not a claim that every nested observation doubles HTTP counters.

### 6.2. `/enrich`: Enrich Information, Keep One Observation

~~~text
http.server.requests
  business.operation=checkout.preview
~~~

There is no child observation. The business tag is found in the HTTP context at stop time:

~~~text
STOP http.server.requests parent=none operation=checkout.preview
OBSERVATIONS /enrich=1
~~~

This is the right approach when the need is solely further classifying an existing request.

In a real application, choose a consistent tag set and value set. A new tag can split metrics into new series even without creating another observation.

### 6.3. `/business`: Child Observation with a Distinct Purpose

~~~text
http.server.requests
└── demo.price.calculate
~~~

The HTTP observation answers questions about the web-layer request. `demo.price.calculate` answers questions about the pricing step and can be reused when that step is called from multiple business flows.

The result has two observations—the same count as `/duplicate`—yet different meaning. Quality cannot be judged merely by node count in the tree.

There is no tracing bridge/exporter in this experiment. The `parent=...` relationship is read from the observation context; it is evidence of the observation relationship, not a snapshot of a trace sent to a backend.

### 6.4. Three Requests, Five Observations

Results summary:

| Endpoint | Stopped observations | HTTP timer recordings |
| --- | --- | --- |
| `/duplicate` | 2 | 1 |
| `/enrich` | 1 | 1 |
| `/business` | 2 | 1 |
| Total | 5 | 3 |

`TOTAL_SERVER_REQUESTS=3` matches the number of incoming requests. Do not sum recording counts across all timers or all observations and call that the "request count."

## 7. Owning the Lifecycle and Preserving Context

### 7.1. The Component Creating an Observation Owns Its Lifecycle

For HTTP observations, the framework starts and stops the observation. Controllers can contribute information, yet must not stop that observation themselves before the framework completes the response.

For business observations it creates itself, application code owns lifecycle management. In synchronous code, `observe(...)` wraps the operation, manages scope, and stops the observation along the execution path.

If managing manually, you must open/close scope, record errors, and stop the observation completely. An observation that has been `start()`ed does not mean it has become the current observation for subsequent code. [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

### 7.2. Use the Same Appropriate Registry

In a Spring Boot application, receive `ObservationRegistry` via dependency injection. Do not create a new registry inside every service just to avoid parent–child relationships. Doing so detaches measurements from the application's shared handlers and configuration.

The lab creates a registry manually because it is a standalone program. In the lab, all components still share that registry and handlers are explicitly registered.

### 7.3. Switching Threads Does Not Eliminate the Need for Parent–Child Relationships

The example only covers synchronous Spring MVC processing. When switching to executors or reactive chains, propagate context using the appropriate mechanism.

Do not fix a missing parent by creating a new root observation on every thread. First verify the context propagation mechanism and subscription/execution timing. With async processing, the true work lifecycle can outlive the returning method call.

Spring Boot supports context propagation, while noting that restoring `ThreadLocal` values in reactive chains depends on configuration. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 8. Process When Detecting Duplicate Instrumentation

1. **Record one concrete execution.** Identify which request or operation produces which observations, rather than looking only at total meter counts.
2. **Locate who owns each measurement point.** Distinguish framework, enabled annotations, manual code, interceptors, and agents.
3. **Compare purpose and boundaries.** The same processing span under two different names can still be redundant.
4. **Choose how to keep needed info.** Remove wrapper layers without a distinct purpose; move tags into context/conventions; keep child observations measuring business steps needing analysis.
5. **Re-verify with evidence.** Ensure request counts, tags, parent–child relationships, and error recording remain accurate after changes.

If redundant observation-creating code cannot be modified immediately, you can use a targeted observation-disabling policy on the Spring Boot-managed registry. That workaround must be verified against the exact name and scope; it does not make the redundant wrapping code disappear.

Do not disable all HTTP observations just because a redundant controller wrapper exists. Deciding to keep or replace the framework mechanism must account for the HTTP metadata, error lifecycle, and context propagation it provides.

If you only filter metrics, the observation lifecycle or tracing branch may still remain. Determine whether duplication is being addressed at the observation, meter, or span layer. Instrumentation provided by standalone agents must also be checked within the agent's own mechanism.

## 9. Common Mistakes

| Practice | Why it easily goes wrong | How to handle |
| --- | --- | --- |
| Putting `@Observed` on every controller to be sure | Can re-wrap operations the framework already observes | Check existing instrumentation and each annotation's purpose |
| Using both `@Observed` and `Observation.observe(...)` around the same operation | Can create two boundaries with the same meaning when the aspect is active | Pick one owner for the measurement point |
| Giving the wrapper a new name and assuming duplication is gone | A different name does not change the unit of work measured | Compare boundaries and diagnostic questions |
| Creating a new observation just to add one tag | Adds an unnecessary lifecycle | Add metadata to the appropriate context |
| Always skipping child observations whenever current is non-null | Loses visibility into distinct business steps | Evaluate the meaning of the child operation |
| Stopping the HTTP observation inside a controller | Ends a framework-owned lifecycle prematurely | Let the framework manage its lifecycle |
| Creating a new registry so no parent appears | Detaches from shared configuration and handlers | Use the injected registry |
| Testing by calling a controller method directly and concluding the framework creates no observation | Bypasses the request's filter chain | Test the proper MVC flow with filters or run the full app |
| Seeing two observations and concluding request count doubled | Confuses counting units across measurements | Read the HTTP timer and each individual observation name |
| Using the lab's `ArrayList` in a multi-threaded server | The example's event recorder is only for sequential verification runs | Use proper handlers/exporters and concurrency-safe structures |

## 10. Self-Verification Exercises

Change one element at a time in the program and re-run:

1. Remove the `demo.controller` wrapper in `duplicate()`, returning only `"120"`. The endpoint should have one HTTP observation and the HTTP timer still records once.
2. Change the tag value in `enrich()` to `checkout.submit`. The observation name and observation count stay unchanged; only the business classification data changes.
3. Add a custom bounded-value tag to `demo.price.calculate`. Verify the tag belongs to the business step; do not assume it is automatically copied onto the HTTP observation.
4. Try calling `duplicate()` directly outside the MockMvc chain and compare. That is a plain Java call rather than a request passing through filters; do not use it to deny the framework's HTTP mechanism.
5. Explain why the total can be five observations while there were only three HTTP requests.
6. For an endpoint in a real project, write down three things before adding instrumentation: unit of work, start/end points, and question to answer. If all three overlap with an existing observation, choose enriching information instead of wrapping again.

An easy-to-use observability design has clear boundaries, clear lifecycle owners, and enough data to answer diagnostic questions. Child observations help when they illuminate part of the work; metadata helps when you only need to understand more about an existing observation.
