# Encapsulating Shared Measurements with MeterBinder

## 1. From Scattered Registration Calls to a Cohesive Metric Set

An image-processing system has two queues: thumbnail generation and search indexing. For each queue, operators need to know:

- How many tasks are waiting?
- How much capacity remains to accept additional tasks?

If each service writes its own registration calls, they might use different names for the same quantity, omit the tag distinguishing queues, or register only half of the metric set. When another application is added, both the convention and the registration code get copy-pasted.

**MeterBinder is a Micrometer contract for encapsulating the registration of a group of meters into a MeterRegistry.** It fits when one component owns multiple related meters or when the same measurement pattern is applied across multiple objects or applications.

Encapsulation here includes the convention: metric names, meter types, metric meanings, tag sets, and how state is read. A good binder keeps applications speaking the same monitoring language.

In this lesson, we build a binder usable across multiple bounded queues, test it in plain Java with Micrometer, and declare it as a bean for Spring Boot Actuator integration.

## 2. Where Does MeterBinder Sit in the Metrics System?

The core contract has the form:

```java
public interface MeterBinder {
    void bindTo(MeterRegistry registry);
}
```

This is an excerpt illustrating the interface; in code, import `io.micrometer.core.instrument.binder.MeterBinder` from Micrometer rather than defining your own interface with the same name.

`bindTo` receives the target registry and registers meters into it. From here, distinguish four responsibilities:

| Component | Responsibility |
| --- | --- |
| Observed business object | Holds state or supplies the figures to measure |
| MeterBinder | Defines and registers a set of meters for that object |
| MeterRegistry | Manages the registered meters |
| Exporting registry and monitoring system | Emits metrics externally, stores, queries, or alerts per configuration |

Conceptual flow:

```text
Queue used by the application
            |
            v
WorkQueueMetrics holds reference and metric set convention
            |
            | bindTo(registry)
            v
MeterRegistry holds Gauges reading the queue
            |
            v
Read locally or export via configured monitoring mechanism
```

A binder **is not a new meter type**. Inside it, you can register Gauges, Counters, Timers, or other appropriate types.

Before writing a custom binder, check whether your technology stack already has built-in meters. Boot may pre-configure metrics for the JVM, web server, or supported libraries. Registering the same metrics again without checking identity can cause conflicts or two confusing ways to measure the same thing.

Nor does it run business work on its own. Registering a Counter inside a binder does not automatically increment the Counter on requests; registering a Timer does not automatically wrap processing methods. There must be corresponding event/timing recording paths. For Gauges in this example, re-reading the queue's existing state is enough to obtain current figures.

## 3. Lock Down the Metric Set Contract Before Writing the Binder

We choose two Gauges:

| Registered name | Tag | Meaning |
| --- | --- | --- |
| `demo.work.queue.depth` | `queue=thumbnail` or `queue=index` | Number of tasks currently in the queue |
| `demo.work.queue.remaining` | Same `queue` tag key | Number of remaining slots able to accept more tasks |

For example, `demo.work.queue.depth{queue=thumbnail}=2` means two tasks are waiting in the thumbnail generation queue. It does not mean two tasks were processed or two tasks are currently running.

Two fixed names express two quantities. Tag values distinguish queues. This lets a single dashboard filter or group by `queue`, rather than needing to know a separate metric name per queue.

Use only tag values controlled by application configuration. Never use individual task IDs, arbitrary URLs, or image filenames as tags. The more tag combinations exist, the more metric series must be managed. See [Micrometer 1.13 naming and tag conventions](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

This metric set targets bounded-capacity queues, such as `ArrayBlockingQueue`. For a practically unbounded queue, `remainingCapacity()` may not carry the intended operational meaning; do not reuse names and descriptions mechanically.

## 4. Writing a Spring-Independent Binder

File `src/example/binder/WorkQueueMetrics.java`:

```java
package example.binder;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.MeterBinder;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;

public final class WorkQueueMetrics implements MeterBinder {

    private final BlockingQueue<?> queue;
    private final Tags tags;

    public WorkQueueMetrics(BlockingQueue<?> queue, String queueName) {
        this.queue = Objects.requireNonNull(queue, "queue");
        String name = Objects.requireNonNull(queueName, "queueName").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("queueName must not be blank");
        }
        this.tags = Tags.of("queue", name);
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Objects.requireNonNull(registry, "registry");

        Gauge.builder("demo.work.queue.depth", this.queue, BlockingQueue::size)
                .tags(this.tags)
                .description("Number of tasks pending in the queue")
                .register(registry);

        Gauge.builder("demo.work.queue.remaining",
                        this.queue, BlockingQueue::remainingCapacity)
                .tags(this.tags)
                .description("Number of remaining slots in the queue")
                .register(registry);
    }
}
```

This design has several noteworthy points.

**The constructor takes the source and configuration without registering meters yet.** Thus you can create the binder before selecting a registry and validate inputs right at configuration time.

**bindTo uses only the registry passed in.** Do not create a private registry and do not use a global static registry. The integrating application decides where measurements go.

**One call registers the entire metric set.** Names and tags are not decided haphazardly across services using the queue.

The registrations inside do not form an auto-rolling-back transaction. If a later call hits a meter-type conflict or configuration error, earlier meters may already have been registered. Therefore, verify the entire set after integration and never swallow registration errors assuming the binder is fully active.

**The class has no Spring dependency.** It can live in a shared Java library, be unit-tested standalone, and be integrated via Spring or invoked directly.

**Each binder is bound to one specific source.** Create another binder for another queue and supply a different `queue` value. Do not mutate the source field after registration.

### Why Hold the Queue in a Field?

With the Gauge form taking an object and a reader function above, Micrometer holds a weak reference to the observed object by default. The binder's `queue` field holds a strong reference. In a Spring application, the binder bean and queue bean have explicit lifecycles.

In a plain Java program, the binder itself or business component must still be kept alive while measuring. Merely calling `new WorkQueueMetrics(...).bindTo(registry)` and dropping all references to both the binder and the source does not guarantee the source remains alive. This behavior is explained in [the Gauge documentation](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

The reader function uses the object parameter passed in by Micrometer via method reference. It does not dequeue tasks, make network calls, or maintain a separate counter that must stay synchronized with the queue.

## 5. Testing Without Spring Boot

### 5.1. Program Using Two Queues and Two Registries

File `src/example/binder/MeterBinderDemo.java`:

```java
package example.binder;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class MeterBinderDemo {

    public static void main(String[] args) {
        BlockingQueue<String> thumbnailQueue = new ArrayBlockingQueue<>(4);
        BlockingQueue<String> indexQueue = new ArrayBlockingQueue<>(2);

        WorkQueueMetrics thumbnailMetrics =
                new WorkQueueMetrics(thumbnailQueue, "thumbnail");
        WorkQueueMetrics indexMetrics =
                new WorkQueueMetrics(indexQueue, "index");

        SimpleMeterRegistry first = new SimpleMeterRegistry();
        SimpleMeterRegistry second = new SimpleMeterRegistry();

        try {
            thumbnailMetrics.bindTo(first);
            indexMetrics.bindTo(first);

            thumbnailQueue.add("image-A");
            thumbnailQueue.add("image-B");

            System.out.println("meters=" + first.getMeters().size());
            System.out.println("thumbnail.depth="
                    + value(first, "demo.work.queue.depth", "thumbnail"));
            System.out.println("thumbnail.remaining="
                    + value(first, "demo.work.queue.remaining", "thumbnail"));
            System.out.println("index.depth="
                    + value(first, "demo.work.queue.depth", "index"));
            System.out.println("index.remaining="
                    + value(first, "demo.work.queue.remaining", "index"));

            thumbnailMetrics.bindTo(first);
            System.out.println("meters-after-rebind=" + first.getMeters().size());

            thumbnailMetrics.bindTo(second);
            System.out.println("second-registry-meters="
                    + second.getMeters().size());

            thumbnailQueue.remove();

            System.out.println("first-registry-thumbnail.depth="
                    + value(first, "demo.work.queue.depth", "thumbnail"));
            System.out.println("second-registry-thumbnail.depth="
                    + value(second, "demo.work.queue.depth", "thumbnail"));
        } finally {
            second.close();
            first.close();
        }
    }

    private static double value(MeterRegistry registry,
                                String name,
                                String queueName) {
        return registry.get(name)
                .tag("queue", queueName)
                .gauge()
                .value();
    }
}
```

This is a complete runnable program when paired with the class in Section 4. `SimpleMeterRegistry` lets you inspect metrics in memory without Prometheus or a monitoring server.

### 5.2. Dependencies and Run Commands

Create `pom.xml` in the root directory of the experiment:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-binder-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

This standalone example requires JDK 17+ and Maven. Downloading dependencies the first time requires Maven Central access. Run from the directory containing `pom.xml`.

PowerShell on Windows:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/binder/WorkQueueMetrics.java src/example/binder/MeterBinderDemo.java
java -cp "out;lib/*" example.binder.MeterBinderDemo
```

On Linux/macOS, the first two commands are identical, and the Java command uses `:` to separate classpath entries:

```bash
java -cp "out:lib/*" example.binder.MeterBinderDemo
```

Stdout from the sequential run:

```text
meters=4
thumbnail.depth=2.0
thumbnail.remaining=2.0
index.depth=0.0
index.remaining=2.0
meters-after-rebind=4
second-registry-meters=2
first-registry-thumbnail.depth=1.0
second-registry-thumbnail.depth=1.0
```

There are four meters in the first registry: two names times two tag values. The second registry only has the `thumbnail` queue's binder attached, so it has two meters.

After removing one task, both registries read `1.0` from the same queue. Two registries do not create two queues and do not split the source's numbers in half.

The counts above apply only to newly created registries in the program with no other filters or binders. A real Boot application's registry also contains many auto-configured meters.

## 6. Letting Spring Boot Auto-Bind Binders

In a Boot 3.3 application with `spring-boot-starter-actuator` and active metrics auto-configuration, declare binders as beans. Let Boot's dependency management choose the Micrometer version; do not force the standalone experiment's version onto an existing application.

File `QueueMetricsConfiguration.java`, using the same `WorkQueueMetrics` class from Section 4:

```java
package example.binder;

import io.micrometer.core.instrument.binder.MeterBinder;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

@Configuration(proxyBeanMethods = false)
public class QueueMetricsConfiguration {

    @Bean
    public BlockingQueue<String> thumbnailQueue() {
        return new ArrayBlockingQueue<>(100);
    }

    @Bean
    public BlockingQueue<String> indexQueue() {
        return new ArrayBlockingQueue<>(50);
    }

    @Bean
    public MeterBinder thumbnailQueueMetrics(
            @Qualifier("thumbnailQueue") BlockingQueue<String> queue) {
        return new WorkQueueMetrics(queue, "thumbnail");
    }

    @Bean
    public MeterBinder indexQueueMetrics(
            @Qualifier("indexQueue") BlockingQueue<String> queue) {
        return new WorkQueueMetrics(queue, "index");
    }
}
```

This is configuration integrated into an existing Boot application, not a standalone `main` class. This package must be scanned or the configuration imported into the application.

The integration flow is:

1. Spring creates the queue beans.
2. The `@Bean` methods create binders with the exact source to measure.
3. Boot's metrics auto-configuration detects `MeterBinder` beans and binds them to the appropriate Spring-managed registry.
4. Business logic uses those queue beans. When task count changes, the Gauges read the updated state.

`@Qualifier` distinguishes two beans of the same type. Without it and without another matching bean selection mechanism, source injection can become ambiguous or pick a different bean than intended.

Per [Boot 3.3's custom metrics registration documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.registering-custom), `MeterBinder` beans are automatically bound to the Spring-managed registry.

**Do not add a manual bindTo call inside @Bean or @PostConstruct when using this automatic path.** Nor do you need to inject `MeterRegistry` into the binder constructor for early registration.

In the plain Java program in Section 5, we called `bindTo` manually because Boot was not orchestrating it. Simply placing an object in a generic Spring container without metrics auto-configuration or an equivalent binder invoker is also not enough to register meters automatically.

### Inspecting via Actuator

With an application already having a web runtime, default port 8080, and default Actuator path, a practice configuration can expose the endpoints to read:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Read each meter by tag:

```bash
curl "http://localhost:8080/actuator/metrics/demo.work.queue.depth?tag=queue:thumbnail"
curl "http://localhost:8080/actuator/metrics/demo.work.queue.remaining?tag=queue:thumbnail"
```

Right after startup, if no tasks have been added to `thumbnailQueue`, the `measurements` section of the two responses gives `0.0` and `100.0` respectively.

These are expected values for the stated configuration and state, not fixed output at every runtime moment. If authentication, a management port, or a custom base path is configured, requests must follow the application's configuration.

The `metrics` endpoint uses the names registered in code. If you omit the tag and multiple queues exist, matching figures may be aggregated; filter by tag when inspecting a specific source. See [the metrics endpoint contract](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

## 7. Distinguishing Binder, Customizer, and Filter

Three mechanisms often appear together yet solve different problems:

| Mechanism | Appropriate job |
| --- | --- |
| `MeterBinder` | Register a set of Gauges for a queue, cache, or pool |
| `MeterRegistryCustomizer` | Configure the registry, such as attaching common environment tags |
| `MeterFilter` | Accept/deny or transform identities and meter configuration upon registration |

In the example, `queue=thumbnail` describes **the observed source**, so it belongs in the binder configuration. Common tags such as deployment environment belong in registry configuration.

If using customizers or filters, register them within the lifecycle Boot supports so they take effect when binders register meters. Do not use a binder to silently reconfigure the shared registry.

[Boot 3.3.0's MeterRegistryPostProcessor source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryPostProcessor.java) shows Boot applies registry configuration before the binder attachment step and handles composite registries specifically. Therefore, do not assume every child registry always receives one direct call from application code.

## 8. Reusing While Preserving Identity and Lifecycle

### 8.1. One Binder Object Can Bind to Multiple Registries

Section 5's example intentionally binds `thumbnailMetrics` to two registries. `bindTo` uses the parameter it receives and does not store a global registry inside the binder.

Do not add an object-wide flag such as:

```java
// Illustrates a flawed design when multiple registries are needed:
if (bound) {
    return;
}
bound = true;
```

That flag can block the second registry from receiving the meters. If a binder genuinely needs to track registrations to manage resources, state must be keyed per registry and thread-safe. Do not use a single boolean flag as a substitute for defining lifecycle.

The binder in this lesson only reads state without starting background threads or registering listeners, so it needs no auxiliary state of this kind.

### 8.2. Duplicate Registration Is Not a Source Replacement Mechanism

In the experiment's default registry, calling the same binder again with the same source, name, and tags does not create extra Gauges. That is why `meters-after-rebind` stays 4.

That result does not mean you can create a new queue, reuse `queue=thumbnail`, and expect the Gauge to switch to reading the new source. The same identity can cause the registry to continue using the existing Gauge.

Two binders observing two different sources must have distinct identities. If two sources share the same name and tags, they collide even when the binder class is identical and the code compiles cleanly.

Filtering/renaming mechanisms can also make initially distinct identities collide. During diagnostics, inspect registry configuration as well.

### 8.3. MeterBinder Has No Automatic Unbind Contract

This interface has only the `bindTo` method. It does not specify that meters are automatically removed once a binder object becomes unreferenced.

The example uses sources that live alongside the application. When the application's registry closes, the overall lifecycle ends as managed by the application.

For queues created and destroyed dynamically at runtime, design a dedicated management component: decide where the source is held, track registered meters per registry, and remove the right meters when observation stops. If measurement listeners or background threads exist, clean them up under the appropriate lifecycle too. Never close the shared registry just to clean up one binder.

Do not create a binder bean per request or per short-lived task. For many transient objects, you typically need a more stable aggregate statistical source and a bounded tag set.

### 8.4. The Same Metric Set Needs the Same Meaning

When placing `WorkQueueMetrics` in a shared library, applications simply provide a queue and a logical name; metric names and tag keys remain consistent.

If `depth` is later changed from “waiting” to “waiting plus in-progress” while keeping the same name, existing charts and alerts can be misinterpreted. Treat metric meaning as part of the library's contract.

For a Counter or Timer that needs event recording, the reuse contract must also specify who calls `increment` or `record`. Never package only meter creation while leaving out the recording path.

## 9. Verifying the Quality of a Binder

A binder can register successfully and still measure the wrong source. When testing, verify both structure and values.

| What to verify | How proved in the example |
| --- | --- |
| Complete set of meters | Each queue has both `depth` and `remaining` |
| Correct names, types, and tags | Locate each Gauge by name and `queue` |
| Reads live state | Enqueue/dequeue tasks and read again |
| Sources are isolated | Mutating `thumbnail` does not change `index` queue |
| No duplicate items on re-bind of same source | Compare `meters-after-rebind` in test registry |
| Does not skip a second registry | Bind the same binder to another registry and read source |
| Boot auto-binds beans | Verify in a context with metrics auto-configuration without manual `bindTo` |
| Input validation | Reject null sources or blank queue names |

`size()` and `remainingCapacity()` are two separate reads. If another thread is mutating the queue concurrently, do not assert that two samples taken at different instants always sum to capacity. Section 5's program runs sequentially, which is why the numbers match the published stdout exactly.

Using concurrent data structures also does not turn an entire set of Gauges into an atomic snapshot. If business logic needs point-in-time consistent figures, design an appropriate snapshot mechanism at the source itself.

Some common symptoms:

| Symptom | Check |
| --- | --- |
| Binder bean exists yet meters are missing | Is metrics auto-configuration active? Was the binder denied by a filter? |
| Meters appear only in a private registry | Did `bindTo` ignore its parameter and use another registry? |
| Two queues report identical unexpected values | Are name/tag sets duplicated or was the wrong source injected? |
| Gauge turns into NaN | Is the source still kept alive? Did the reader throw an exception? |
| Second registry lacks the metric set | Is there an object-wide `bound` flag or state tied only to the first registry? |
| Time-series count grows per task | Were task IDs or arbitrary data passed into tags? |

## 10. Practice Exercises

1. Run the two Java classes from Sections 4–5 and verify all nine lines of stdout.
2. Add a task to `indexQueue`. Verify `index.depth=1.0` and `index.remaining=1.0`, while the `thumbnail` source keeps its state.
3. Create another binder for an `archive` queue in the test registry. Without filters and with correct names/tags, the total number of Gauges across three queues is six.
4. In a separate experiment, intentionally reuse the same tag value for two different queues. Observe which source the Gauge reads and explain why distinct identities are required.
5. Integrate Section 6's configuration into Boot and confirm all four Gauges appear without adding a manual `bindTo` call. Filter by tag to read each queue.
6. Before moving a binder into a shared library, document each meter's meaning, allowed tag set, source lifecycle, and how applications integrate it.

The desired outcome is a metric set reusable across other sources, registered into the right registry, and preserving consistent metric meaning across every application that uses it.
