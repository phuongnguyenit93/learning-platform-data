# Registering a Gauge and Managing the Lifecycle of the Observed Object

## 1. What Does a Gauge Measure in Custom Metrics?

Suppose an application sends emails through a queue with a capacity of 100 tasks. Operators want to know **how many tasks are currently waiting**, rather than only how many tasks have been accepted since startup. This is a quantity suited to `Gauge`: the value rises when work is added and falls when work is taken out.

In Micrometer, distinguish three components:

- **Observed object**: a queue, cache, or an object holding the current figure.
- **Reader function**: extracts a number from that object, such as `BlockingQueue::size`.
- **Gauge**: the registered meter in `MeterRegistry`, associating a name and grouping tags with the reader function.

Think of registering a Gauge like placing a meter next to a queue: the meter must know which queue to read, and the application must ensure that queue stays alive for as long as measurement is needed.

| Question to answer | Appropriate meter type |
| --- | --- |
| How many tasks are currently waiting? | Gauge reading queue size |
| How many tasks have been received in total? | Counter |
| How long does one task take to process? | Timer |
| How many tasks were processed in a time interval? | Cumulative data from a Counter or Timer's recorded count, combined with monitoring system queries |

This lesson focuses on the relationship between **meter registration, object references, and lifecycle termination**. There is no need to build a business API solely to demonstrate a Gauge.

## 2. A Gauge Reads the Value When Observed

A standard Gauge does not store a full history of every change to the object. When the meter is read, the registered function is invoked to retrieve the current value.

For example, suppose queue depth changes as follows:

```text
First read:                   1
Between two reads:            2 -> 3 -> 2
Second read:                  1
```

If you read only at the beginning and end, the observer receives `1` and `1`. You cannot infer that the queue never held three items. To know total throughput or processing latency, additional appropriate meters are required.

Registering a Gauge also does not spawn a separate background thread per meter. Sampling times depend on the registry and monitoring system's scrape/export mechanism. In the `SimpleMeterRegistry` example below, the program explicitly calls `value()` to verify.

Because the reader function can run concurrently with business threads, both the object and the read operation must be concurrency-safe. Using a non-thread-safe collection and merely wrapping it in a Gauge does not make that collection safe. For a simple numeric source, `AtomicInteger` or `AtomicLong` is often convenient; for a queue, use an appropriate queue implementation and read the exact state the business logic uses.

The [Micrometer 1.13 documentation on Gauges](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html) describes the sampling model and supported observable data sources.

## 3. Registering the Right Data Source

### 3.1. Builder Returning a Gauge

The snippet below illustrates registration and is not yet a standalone runnable program:

```java
AtomicInteger pending = new AtomicInteger(0);

Gauge gauge = Gauge.builder("demo.jobs.pending", pending, AtomicInteger::get)
        .tag("queue", "email")
        .description("Number of tasks pending in the email queue")
        .register(registry);

pending.set(7);
double current = gauge.value(); // 7.0 at this read time
```

Here, `pending` holds mutable state. `gauge` represents the meter. To change the state, update `pending`; do not look for a `set()` method on the Gauge.

With a real queue, prefer measuring `queue.size()` directly instead of maintaining a separate counter variable unless necessary. A second counter can drift out of sync with the queue when enqueuing fails, taking a task is cancelled, or an error branch forgets to update it.

### 3.2. Convenience Method with a Different Return Type

```java
AtomicInteger pending = registry.gauge(
        "demo.jobs.pending", new AtomicInteger(0));

pending.set(7);
```

With this overload, the return value is **the observed numeric object**, not a `Gauge`. Store it in a field of a sufficiently long-lived component so you both update it and keep the measurement source alive.

Do not use both examples to register the same metric with different objects. They are two alternative ways to meet the same need.

### 3.3. Do Not Register a Snapshot Value

```java
// Wrong if you want to track future changes of the queue:
registry.gauge("demo.queue.depth", queue.size());
```

`queue.size()` is evaluated immediately when calling the method. The numeric value passed in retains no link to future changes of `queue`. Similarly, an `Integer` or `Double` is an immutable object; reassigning a variable to another number does not change the object that the Gauge is measuring.

The right expression is passing a **re-readable source**:

```java
Gauge.builder("demo.queue.depth", queue, BlockingQueue::size)
        .tag("queue", "email")
        .register(registry);
```

The short snippets in this section assume `registry` and Java types are already imported. Section 5 provides complete files and run commands.

## 4. Why Must You Manage the Lifecycle of the Measurement Source?

### 4.1. Holding the Gauge Does Not Hold the Object

With the builder form taking an object and a reader function, Micrometer holds a **weak reference** to the observed object by default. A weak reference does not force the object to stay in memory once the application has no strong reference path to it.

The required model in a Spring application can be represented as:

```text
ApplicationContext
    -> metrics management bean
        -> queue                            (strong reference)

MeterRegistry
    -> Gauge
        --weak reference--> queue
        -> reader function BlockingQueue::size
```

The bean holds the queue so business logic and the metric share it. The Gauge only observes that source.

The illustration below has a lifecycle problem:

```java
void register(MeterRegistry registry) {
    AtomicInteger temporary = new AtomicInteger(0);
    Gauge.builder("demo.temporary.pending", temporary, AtomicInteger::get)
            .register(registry);
}
```

When the method returns, if nothing else holds `temporary`, the object can be reclaimed by the garbage collector (GC). The registry still holding the Gauge does not fix that. Saving the Gauge itself in a field also does not replace the responsibility of keeping the measurement source alive.

After the source is collected, the Gauge may report `NaN` or disappear from exported data, depending on the registry. **Do not interpret this condition as the value 0.** An empty queue and an unreadable queue are two different states.

In [Micrometer 1.13.0 DefaultGauge](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/internal/DefaultGauge.java), exceptions in the reader function can also lead to `NaN`. Therefore, `NaN` is a signal to check both the source and the reader function, not sole proof of GC.

Do not write tests assuming that calling `System.gc()` once will reclaim an object immediately. GC timing is not a stable condition for verifying business behavior.

### 4.2. Avoid Unintentionally Retaining the Source via a Lambda

These two forms differ in their reference paths:

```java
// Reader function uses the exact object Micrometer passes in:
Gauge.builder("demo.queue.depth", queue, BlockingQueue::size)
        .register(registry);

// Lambda captures an additional external object:
Gauge.builder("demo.queue.depth.captured", queue, ignored -> queue.size())
        .register(registry);
```

In the second form, the reader function captures `queue`. Because the Gauge holds the reader function, the reference path through the lambda can keep the queue alive unexpectedly long. A weak reference along one path does not cancel a strong reference along another path.

Prefer a reader function that uses the parameter it receives. When a source must live long, express that through a field of the component managing the source, rather than relying on the side effect of variable capture.

### 4.3. When Deliberately Using strongReference(true)

The builder in Micrometer 1.13 provides an option to strongly hold the measurement source:

```java
AtomicInteger state = new AtomicInteger(5);

Gauge retained = Gauge.builder(
                "demo.explicit.pending", state, AtomicInteger::get)
        .strongReference(true)
        .register(registry);
```

This option is useful when the design deliberately delegates source retention to the meter. It must come with a decision on when the source will be released and who is responsible for removing the meter.

If the registry is long-lived, the source and objects it references can remain alive just as long. Do not enable this option indiscriminately to mask unclear state ownership. Nor does it fix updating the wrong object or duplicate name/tag registrations.

After removing the Gauge, the source is eligible for collection only if no other strong references remain; for instance, the `retained` variable or a business component might still hold related objects. Removing the meter does not force GC to run.

## 5. Complete Program: Queue Lives Alongside Its Metrics Component

The example uses Java 17 or later and Micrometer 1.13.0. The two Java files below form a standalone program with no Spring or external monitoring system required.

In a Spring Boot 3.3 project, let Boot's dependency management choose the compatible Micrometer version. The pinned version below is solely for standalone experimentation.

### 5.1. Component Retaining the Source and Registering Once

File `src/example/metrics/QueueDepthMetrics.java`:

```java
package example.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;

public final class QueueDepthMetrics implements AutoCloseable {

    private final MeterRegistry registry;
    private final BlockingQueue<String> queue;
    private final Gauge gauge;

    public QueueDepthMetrics(MeterRegistry registry,
                             BlockingQueue<String> queue) {
        this.registry = Objects.requireNonNull(registry);
        this.queue = Objects.requireNonNull(queue);
        this.gauge = Gauge.builder(
                        "demo.queue.depth", this.queue, BlockingQueue::size)
                .tag("queue", "email")
                .description("Number of tasks pending in the email queue")
                .register(this.registry);
    }

    public double value() {
        return this.gauge.value();
    }

    @Override
    public void close() {
        this.registry.remove(this.gauge);
    }
}
```

The `queue` field strongly holds **the exact queue being measured**. The `BlockingQueue::size` function does not capture an external queue. The `value()` method is exposed so the experiment can read it directly; business processing does not need to call this method continuously.

`close()` removes only this component's meter; it does not close the shared registry and does not clear tasks from the queue.

**Precondition:** within a single registry, only one component should manage the name/tag set `demo.queue.depth{queue=email}` at a time. Do not instantiate multiple `QueueDepthMetrics` with the same name/tag set, as they would share one meter and remove each other's meter by mistake.

### 5.2. Mutating the Queue and Reading Back

File `src/example/metrics/GaugeLifecycleDemo.java`:

```java
package example.metrics;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public final class GaugeLifecycleDemo {

    public static void main(String[] args) {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(10);

        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            try (QueueDepthMetrics metrics =
                         new QueueDepthMetrics(registry, queue)) {

                System.out.println("initial=" + metrics.value());

                queue.add("A");
                queue.add("B");
                System.out.println("after-add=" + metrics.value());

                queue.remove();
                System.out.println("after-remove=" + metrics.value());

                queue.add("C");
                queue.add("D");
                queue.remove();
                queue.remove();
                System.out.println("after-burst=" + metrics.value());
            }

            boolean registered = registry.find("demo.queue.depth")
                    .tag("queue", "email")
                    .gauge() != null;
            System.out.println("registered-after-close=" + registered);
        } finally {
            registry.close();
        }
    }
}
```

The program runs sequentially so stdout is completely deterministic. Choosing `ArrayBlockingQueue` also makes this source suitable when multiple threads later enqueue and dequeue work.

### 5.3. Dependencies and Compile Commands

Create `pom.xml` in the root directory of the experiment:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>gauge-lifecycle-demo</artifactId>
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

Run in the directory containing `pom.xml`, with JDK 17+ and Maven in PATH. Downloading dependencies the first time requires Maven Central access.

PowerShell on Windows:

```powershell
mvn -q org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies -DoutputDirectory=lib
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/example/metrics/QueueDepthMetrics.java src/example/metrics/GaugeLifecycleDemo.java
java -cp "out;lib/*" example.metrics.GaugeLifecycleDemo
```

With Bash on Linux/macOS, keep the first two commands the same and change the classpath separator in the run command:

```bash
java -cp "out:lib/*" example.metrics.GaugeLifecycleDemo
```

Stdout:

```text
initial=0.0
after-add=2.0
after-remove=1.0
after-burst=1.0
registered-after-close=false
```

Between `after-remove` and `after-burst`, the size briefly reached 3 and returned to 1. Because the Gauge is only read after the sequence of operations, the result is still `1.0`. The last line proves the meter was removed from the registry; it does not prove the queue has been collected by GC. In Micrometer 1.13.0, the registry has a `close()` method without implementing `AutoCloseable`, so the example closes the registry in `finally` and uses try-with-resources only for `QueueDepthMetrics`.

## 6. Tying Lifecycle into Spring Boot Actuator

In a Spring Boot application that already has `spring-boot-starter-actuator`, use the Spring-managed `MeterRegistry`. Do not create a private `SimpleMeterRegistry` inside a business bean and expect Actuator to automatically see metrics there.

Keep the `QueueDepthMetrics` class above and add the following configuration in a package scanned by the application:

File `QueueMetricsConfiguration.java`:

```java
package example.metrics;

import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

@Configuration(proxyBeanMethods = false)
public class QueueMetricsConfiguration {

    @Bean
    public BlockingQueue<String> emailQueue() {
        return new ArrayBlockingQueue<>(100);
    }

    @Bean(destroyMethod = "close")
    public QueueDepthMetrics emailQueueMetrics(
            MeterRegistry registry,
            @Qualifier("emailQueue") BlockingQueue<String> queue) {
        return new QueueDepthMetrics(registry, queue);
    }
}
```

This is integration configuration, not a standalone Boot application. It uses the class from Section 5 and the registry configured by Actuator.

The lifecycle relationships are clear:

1. Spring creates the queue bean.
2. Spring creates the `emailQueueMetrics` bean, passing that same queue and registry into the constructor.
3. The metrics bean registers the Gauge once and holds the source via its `queue` field.
4. Business code receives the `emailQueue` bean to enqueue/dequeue tasks; the Gauge reads that exact queue.
5. When the context shuts down normally, Spring calls `close()` via `destroyMethod`, removing the Gauge.

Do not place registration inside every request or every task submission. Nor should you call `close()` yourself while the bean is still expected to serve measurements.

If you organize via `MeterBinder`, a binder bean can group meters that depend on other beans and Boot will bind it to the registry automatically. Choose one registration path per name/tag set to avoid duplicate registration. See [registering custom metrics in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.registering-custom) and [Spring bean lifecycle callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle).

### Inspecting via the metrics Endpoint

If the application already runs in a web environment and endpoints are not otherwise configured, you can add to your practice configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

When the application uses the default port and default Actuator base path:

```bash
curl "http://localhost:8080/actuator/metrics/demo.queue.depth?tag=queue:email"
```

When the queue has no tasks yet, the corresponding measurement portion looks like:

```json
{
  "measurements": [
    {
      "statistic": "VALUE",
      "value": 0.0
    }
  ]
}
```

This is an **excerpt** of the response, not the full JSON. Other fields such as name, description, and tags may appear. If the application has Spring Security, the request must also satisfy the application's authentication/authorization configuration.

Use the registered name `demo.queue.depth` to query this endpoint. When exported to another system, the displayed name may be normalized according to that system's conventions. The tag parameter selects the right queue when multiple series exist. Endpoint details and tag filtering are described in [the metrics endpoint documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.endpoint).

## 7. Duplicate Registration and Swapping Objects: Two Mistakes Easily Confused with GC

### 7.1. Same Name and Tags Does Not Replace the Measurement Source

Within the same registry, re-registering a Gauge with the same name and tag set is not an instruction to update the observed object. Suppose:

```java
AtomicInteger first = new AtomicInteger(2);
AtomicInteger second = new AtomicInteger(9);

Gauge original = Gauge.builder(
                "demo.pending.same", first, AtomicInteger::get)
        .tag("queue", "email")
        .register(registry);

Gauge repeated = Gauge.builder(
                "demo.pending.same", second, AtomicInteger::get)
        .tag("queue", "email")
        .register(registry);

first.set(4);
second.set(12);
```

With a registry that accepts the meter and no special filter configuration, the existing meter continues tracking `first`, so reading the value yields `4.0`. `second` does not become the new source merely because it was passed in the later registration. The registry may log a warning about duplicate registration.

The practical consequence: you update `second`, yet the meter does not change, leading to the mistaken conclusion that Gauge caches values or exports slowly.

If `MeterFilter` configuration maps two name/tag sets to the same identity, the same collision can occur. Names and tags in your design must distinguish genuinely different sources.

### 7.2. Reassigning a Field to a New Object Does Not Change the Registered Source

Suppose at startup the Gauge is registered with `queueA`. Later the program reassigns the queue variable to `queueB`. The Gauge remains bound to `queueA` received at registration time.

There are two approaches, depending on design:

- Keep one stable source throughout the meter's lifecycle, mutating the contents inside that source.
- When a source is genuinely replaced, have the component managing the source coordinate removing the old Gauge and registering the new source.

If swapping sources is a frequent system capability, you can also design a stable intermediate object that reads the current source. In that case, ensure swapping/reading the source is thread-safe and define behavior clearly when no source is present.

Do not repeatedly remove and re-register on every task's processing path. Swapping sources and removing meters must be owned by one responsible component; if threads do it independently, you can create observation gaps or remove a meter just created by another thread.

## 8. Lifecycle Termination and Diagnostics

For an object that lives as long as the application, a bean strongly holding the source is usually sufficient. For objects created and destroyed while the application is running, you must also define when to stop observing them.

**A reclaimed source does not mean the meter was automatically removed from the registry.** An old registration entry can remain while unable to read the source. If you later create a new object and re-register under the same name/tags, you can also hit the duplicate registration problem.

When a dynamic source reaches end of life, the design sequence should be: coordinate stopping business use of the source, remove the Gauge belonging to that source, and then release unnecessary strong references. Historical data already stored by the monitoring system is not erased merely because the application calls `registry.remove(gauge)`.

Do not create tags from request IDs, individual email addresses, or arbitrary identifiers just to avoid collisions. Every tag combination creates an extra metric series; removing a Gauge in the application also does not make external history vanish immediately. The example uses the `queue=email` tag with a controlled value count.

| Symptom | Check first | Appropriate fix |
| --- | --- | --- |
| Initially reports numbers, then NaN or missing samples | Is there still a strong reference to the exact source? Did the reader throw? | Fix source lifecycle or reader error; do not arbitrarily turn into 0 |
| Updating a variable leaves Gauge unchanged | Does that variable point to the exact registered object? | Update the stable source; handle source replacement explicitly |
| Re-registered yet still reads the old number | Were the same name/tags reused? | Register once; remove/re-register only when actively replacing the source |
| Memory grows with number of created objects | Did a lambda capture a large object? Was strongReference enabled and never removed? | Review reference paths and cleanup ownership |
| Values occasionally wrong under concurrency | Are the source and reader operation concurrency-safe? | Choose appropriate data structures/synchronization |
| Readable internally yet missing from Actuator | Is the meter in the Spring-managed registry? Is the endpoint exposed? | Use the injected registry and check endpoint configuration |
| Short-lived spikes do not appear | Did they happen between two scrapes? | Add complementary meters suited to the question |

The reader function should be fast, side-effect-free, and perform no business work. Avoid making network calls, running heavy queries, or dequeuing items just to return a number. An observation must never accidentally alter the quantity being measured.

## 9. Self-Verification Practice

1. Run the program in Section 5 and verify all five lines of stdout.
2. Move the `after-burst` read to immediately after the two `add` calls for `C` and `D`. The value at that point is `3.0`; explain why the earlier read only saw `1.0`.
3. In a separate test registry, run the duplicate registration snippet from Section 7.1 and verify which object is actually measured. Do not mix this meter with the queue program's Gauge.
4. Integrate the configuration from Section 6 into a Boot application, enqueue two items via the queue bean, and query by tag. While two items are waiting and no worker thread takes them, the value must be `2.0`.
5. Inspect one metrics component in your application and identify: who holds the source, who mutates the source, who registers the meter, and who removes the meter. If any of those cannot be answered, the lifecycle design lacks clear ownership.

A trustworthy Gauge requires simultaneously getting right the **meaning of the quantity**, the **object being read**, the **lifetime of the source**, and the **responsibility for removing the meter**.
