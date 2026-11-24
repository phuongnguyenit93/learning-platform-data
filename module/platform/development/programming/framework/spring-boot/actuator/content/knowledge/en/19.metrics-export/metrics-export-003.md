# Combining Multiple Registries and the Role of the Global Registry

A service needs Prometheus to scrape the count of received orders while simultaneously sending that measurement over OTLP. Order processing code can record once via Micrometer. Where measurements go depends on which registry the calling code uses and which target registries are attached to it.

## Target Registries, Composite, and Global Registry

| Component | Role | How Application Code Uses It |
| --- | --- | --- |
| Target registry, e.g., `PrometheusMeterRegistry` or `OtlpMeterRegistry` | Holds and formats measurements according to the conventions of one monitoring system. | Used directly when a target-specific feature is needed, such as obtaining Prometheus scrape output. |
| `CompositeMeterRegistry` | Groups multiple registries. Incrementing a counter via the composite forwards that increment to attached target registries that accept the meter. | Registers and updates meters through a single application entry point. |
| `Metrics.globalRegistry` | A static Micrometer composite. It maintains its own set of target registries, shared across callers using the `Metrics` class. | Static calls like `Metrics.counter(...)` or `Metrics.timer(...)` go through this composite. |

A composite forwards **write operations**. Each target still applies its own naming conventions, units, filters, and export behavior. For instance, Prometheus reads on a scrape interval, while OTLP sends data on a configured step. The two systems may display values at different times even though they receive writes from the same counter. When you need to check what each target received, inspect that specific target registry. Calling `count()` on a composite counter in Micrometer 1.13 reads from a single child registry, so that value cannot be used to verify all targets at once.

A meter can be registered before target registries are added. When a new registry is attached, the composite creates the corresponding meter there. Increments recorded before attachment are not replayed. When a composite is empty, writes to its counters have no destination.

## How Spring Boot 3.3 Wires Registries

Spring Boot Actuator auto-configures supported registries when the corresponding dependency is present and export properties allow it. When multiple `MeterRegistry` beans exist and there is no single candidate to inject, Spring Boot creates a primary `CompositeMeterRegistry` containing the target registries. When only a single suitable candidate exists, that bean can be injected directly. Auto-configured `SimpleMeterRegistry` serves as an in-memory fallback when no other registry is present.

In a web application, for example, use both of the following dependencies and let Spring Boot manage versions.

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
    runtimeOnly 'io.micrometer:micrometer-registry-otlp'
}
```

With an OTLP HTTP receiver running on the same machine at port 4318, you can place the following configuration in `application.properties`.

```properties
management.endpoints.web.exposure.include=health,prometheus
management.otlp.metrics.export.url=http://localhost:4318/v1/metrics
management.metrics.use-global-registry=false
```

Prometheus is configured separately to scrape `/actuator/prometheus`. The OTLP registry sends to the configured URL. `management.metrics.use-global-registry=false` disables Spring Boot's automatic wiring of Spring-managed registries into `Metrics.globalRegistry`. Individual export enable/disable flags operate independently. The injected `MeterRegistry` bean still writes to the Spring-configured targets.

By default, Spring Boot attaches its registries to the global registry, so legacy code calling `Metrics.counter(...)` can still send measurements to the application's targets. When that flag is set to `false`, static calls still go to the global registry and only reach targets attached by other means, such as manual configuration in a library.

For application-owned code, use constructor injection to receive `MeterRegistry` from Spring and hold registered meters in fields. The example below is a component placed within the application's component-scan scope.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {
    private final Counter accepted;

    public OrderMetrics(MeterRegistry registry) {
        accepted = registry.counter("orders.accepted");
    }

    public void recordAcceptedOrder() {
        accepted.increment();
    }
}
```

Call `recordAcceptedOrder()` once after an order is accepted. Registry customization beans, such as `MeterRegistryCustomizer` for common tags or `MeterFilter` for filtering meters, belong to the Spring-managed configuration. Injecting the registry keeps the write path tied to application configuration and allows substituting a dedicated registry in tests.

## Experiment with Two In-Memory Registries

The following program runs standalone with Java 17+ and `io.micrometer:micrometer-core:1.13.0` along with its runtime dependencies. Two `SimpleMeterRegistry` instances act as two targets. The program manually attaches and detaches the global registry to observe write routing without starting a monitoring server.

Save the file `RegistryRouting.java`.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.composite.CompositeMeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.Locale;

public class RegistryRouting {
    public static void main(String[] args) {
        CompositeMeterRegistry application = new CompositeMeterRegistry();
        SimpleMeterRegistry first = new SimpleMeterRegistry();
        SimpleMeterRegistry second = new SimpleMeterRegistry();
        Counter business = application.counter("orders.accepted");
        Counter legacy = Metrics.counter("legacy.orders.accepted");

        try {
            business.increment(10);
            legacy.increment(10);
            application.add(first);
            business.increment(2);
            application.add(second);
            printCounts("late-join", "orders.accepted", first, second);
            System.out.println("global-meter-before-link="
                    + (first.find("legacy.orders.accepted").counter() != null));

            business.increment(3);
            Metrics.addRegistry(application);
            legacy.increment();
            printCounts("application", "orders.accepted", first, second);
            printCounts("global-linked", "legacy.orders.accepted", first, second);

            Metrics.removeRegistry(application);
            legacy.increment(10);
            business.increment();
            printCounts("application-after-unlink", "orders.accepted", first, second);
            printCounts("global-unlinked", "legacy.orders.accepted", first, second);
        } finally {
            Metrics.removeRegistry(application);
            Metrics.globalRegistry.remove(legacy);
            application.close();
            first.close();
            second.close();
        }
    }

    private static void printCounts(String stage, String name,
            SimpleMeterRegistry first, SimpleMeterRegistry second) {
        System.out.printf(Locale.ROOT, "%s first=%.0f second=%.0f%n", stage,
                first.get(name).counter().count(), second.get(name).counter().count());
    }
}
```

In Bash, set `MICROMETER_CP` to the classpath containing the runtime JARs that Maven or Gradle resolves for `micrometer-core:1.13.0`.

```bash
javac --release 17 -cp "$MICROMETER_CP" RegistryRouting.java
java -cp ".:$MICROMETER_CP" RegistryRouting
```

Output with Micrometer 1.13.0.

```text
late-join first=2 second=0
global-meter-before-link=false
application first=5 second=3
global-linked first=1 second=1
application-after-unlink first=6 second=4
global-unlinked first=1 second=1
```

- `late-join` shows that the first 10 increments occurred while the composite was empty. The first registry received 2 increments after being attached. The second registry was attached later and started at 0.
- `global-meter-before-link=false` shows that the first registry did not yet have the meter from the static call. After attaching the application's composite to the global registry, both registries received 1 new increment from that meter.
- After detaching the global link, a write through the application composite still increments both targets. Both values of the static meter remain at 1 because the new increment went into the now-empty global registry.

## Troubleshooting Missing or Double-Counted Measurements

1. **Identify where the call goes.** Check whether the code uses `registry.counter(...)` from the Spring bean, `Metrics.counter(...)` from global, or directly calls a target registry.
2. **Check attachment and registration timing.** Inspect the injected `MeterRegistry` bean type and `getRegistries()` if the bean is a composite. If using global, also check `Metrics.globalRegistry.getRegistries()`. Compare when the target was attached with when events were recorded.
3. **Inspect each target individually.** Verify whether the meter is accepted by filters, check its exported name and tags, and then check the corresponding scrape or OTLP export. One registry having data can still coexist with another target failing due to configuration or connectivity.
4. **Look for two writes for the same event.** When both Spring's composite and the global registry are linked to the same target registries, calling both APIs for the same event with the same name and tags can increment the counter twice in each target. Choose a single write path for that event.

## References

- [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer — Registries, Composite, and Global Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Spring Boot 3.3.0 — Composite Registry Configuration](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/CompositeMeterRegistryConfiguration.java)
- [Spring Boot 3.3.0 — Linking Registries to the Global Registry](https://github.com/spring-projects/spring-boot/blob/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryPostProcessor.java)
