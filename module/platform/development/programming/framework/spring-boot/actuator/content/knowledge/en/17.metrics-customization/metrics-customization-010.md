## Distinguishing Global Observation Configuration from Per-Meter Configuration

A checkout service needs to attach deployment region to observation data so charts can be correlated with traces. The service also needs to count how many checkouts complete within 300 ms. The first requirement concerns metadata describing the observed operation. The second requirement concerns how a duration instrument (`Timer`) aggregates samples.

### Two Configuration Layers in Actuator

An `Observation` describes a single execution of work, such as a checkout operation. `ObservationRegistry` holds rules applied when creating and processing Observations. Handlers (`ObservationHandler`) share that context to produce appropriate signals. When Actuator metrics configuration is active, `DefaultMeterObservationHandler` records completion time into a `Timer`. When Micrometer Tracing is enabled with a corresponding handler, an Observation can also create a span in a trace.

`MeterRegistry` manages meters, such as `Timer`, `Counter`, and `Gauge`. A meter can originate from an Observation, from direct registration in code, or from a library's metrics binder. Therefore, configuration applied to meters can affect data from multiple sources as long as the meter ID matches. With `DefaultMeterObservationHandler`, the completed `Timer` derives its name from the Observation name and its labels from low-cardinality key-values, plus the error label added by the handler.

| What Needs to Change? | Configuration or Extension Point | Scope of Impact |
| --- | --- | --- |
| Attach `region` to Observations | `management.observations.key-values.region` | Adds a low-cardinality key-value pair to the Observation context. Handlers can use it in metrics and traces. |
| Stop observing a family of operations | `management.observations.enable` or `ObservationPredicate` | A disabled Observation does not go through its handlers' lifecycle. The business block still executes. |
| Attach `service` to meters | `management.metrics.tags.service` | Adds a common label at the meter layer, including directly registered meters. |
| Change histogram, percentile, or SLO thresholds of a meter family | `management.metrics.distribution.*` or `MeterFilter.configure(...)` | Tunes how compatible distribution meters such as `Timer` and `DistributionSummary` aggregate samples. |
| Deny registration of a meter family | `management.metrics.enable` or `MeterFilter.accept(...)` | Affects meter registration. Other Observation handlers can still run. |

With the default handler, low-cardinality pairs such as `channel=web` are suitable as metric labels. Order IDs can take very many values and thus belong to high cardinality. The default metrics handler does not promote that group into metric labels. With appropriate tracing configuration, a tracing handler can record it on a span. Choose one place to set each shared attribute according to the desired scope. For instance, place `region` at the Observation layer if needed on both signals originating from Observations, or place it at the meter layer if needed as a label on every meter, including directly registered ones.

### Reading Configuration by Scope

Example for Spring Boot 3.3:

```yaml
management:
  observations:
    key-values:
      region: ap-southeast-1
    enable:
      "[checkout.internal]": false
  metrics:
    tags:
      service: checkout
    enable:
      "[checkout.debug.cache]": false
    distribution:
      slo:
        "[checkout.pay]": 300ms
```

- `region` enters the context of processed Observations. `service` enters meter labels, including a directly registered `Timer`.
- `checkout.debug.cache` can still be observed, yet `MeterRegistry` denies the meter matching the rule. By contrast, `checkout.internal` is a prefix that disables Observations, so `checkout.internal.heartbeat` will not invoke handlers for that Observation.
- `slo` adds a 300 ms boundary to the matching checkout payment timer. That boundary serves to count samples not exceeding the threshold. The refund timer still records durations normally and does not receive this boundary.

In `management.metrics.distribution.*`, Spring Boot 3.3 looks up each property by meter name and progressively strips trailing dot-delimited segments to find a matching prefix. For example, the key `checkout.pay` applies both to meters with that name across multiple tag combinations and to child names such as `checkout.pay.active` if the meter type supports the property. A more specific key `checkout.pay.card` takes precedence for that property on matching names. When targeting only an exact name, a specific meter type, or a label value such as `channel=web`, use a `MeterFilter` inspecting `Meter.Id` and register the filter before the meter is created. When customizing distribution in `configure(...)`, merge the new configuration with the incoming configuration to preserve properties not overridden.

The name used in configuration keys is the Micrometer meter name. For example, with Prometheus, `checkout.pay` is the name matched in configuration, while `checkout_pay_seconds_bucket` is the histogram series name in exporter output. For custom `Observation` instances, `contextualName(...)` describes the operation in context, while the default metrics handler derives the meter name from the Observation name.

### Runnable Experiment with Java 17

Save the YAML above as `application.yml` and the Java code below as `ObservationScopeDemo.java` in the same directory. The program starts Spring Boot 3.3.0 with an in-memory metrics registry, registers a handler recording completed Observation names, and runs four operations. The test handler only confirms the Observation lifecycle. The program does not configure a trace exporter.

```java
package demo;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.builder.SpringApplicationBuilder;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

@SpringBootConfiguration
@EnableAutoConfiguration
public class ObservationScopeDemo {
    public static void main(String[] args) {
        try (var app = new SpringApplicationBuilder(ObservationScopeDemo.class)
                .web(WebApplicationType.NONE)
                .bannerMode(Banner.Mode.OFF)
                .logStartupInfo(false)
                .properties("logging.level.root=OFF")
                .run(args)) {
            var observations = app.getBean(ObservationRegistry.class);
            var meters = app.getBean(MeterRegistry.class);
            List<String> completed = new ArrayList<>();
            observations.observationConfig().observationHandler(new ObservationHandler<Observation.Context>() {
                @Override
                public boolean supportsContext(Observation.Context context) {
                    return true;
                }

                @Override
                public void onStop(Observation.Context context) {
                    completed.add(context.getName());
                }
            });

            observe(observations, "checkout.pay");
            observe(observations, "checkout.refund");
            observe(observations, "checkout.debug.cache");
            observe(observations, "checkout.internal.heartbeat");

            Timer direct = meters.timer("checkout.internal.heartbeat");
            direct.record(Duration.ofMillis(40));
            Timer pay = meters.get("checkout.pay").timer();
            Timer refund = meters.get("checkout.refund").timer();

            System.out.println("completed=" + completed);
            System.out.printf("pay count=%d region=%s service=%s order.id=%s buckets=%d%n",
                    pay.count(), pay.getId().getTag("region"), pay.getId().getTag("service"),
                    pay.getId().getTag("order.id"), pay.takeSnapshot().histogramCounts().length);
            System.out.printf("refund count=%d buckets=%d%n",
                    refund.count(), refund.takeSnapshot().histogramCounts().length);
            System.out.println("debug timer present="
                    + (meters.find("checkout.debug.cache").timer() != null));
            System.out.printf("direct count=%d region=%s service=%s%n",
                    direct.count(), direct.getId().getTag("region"), direct.getId().getTag("service"));
        }
    }

    private static void observe(ObservationRegistry registry, String name) {
        Observation.createNotStarted(name, registry)
                .lowCardinalityKeyValue("channel", "web")
                .highCardinalityKeyValue("order.id", "example-104")
                .observe(() -> System.out.println("work=" + name));
    }
}
```

Use Maven or Gradle to resolve a classpath with `org.springframework.boot:spring-boot-starter-actuator:3.3.0` and `com.fasterxml.jackson.core:jackson-databind:2.17.1`, along with their transitive dependencies. Set `CP` to that classpath and run from the directory containing both files. The commands below use Bash. In PowerShell, use `$env:CP` and `;` as the classpath separator.

```bash
javac -cp "$CP" -d . ObservationScopeDemo.java
java -cp ".:$CP" demo.ObservationScopeDemo --spring.config.location=file:./application.yml
```

Output:

```text
work=checkout.pay
work=checkout.refund
work=checkout.debug.cache
work=checkout.internal.heartbeat
completed=[checkout.pay, checkout.refund, checkout.debug.cache]
pay count=1 region=ap-southeast-1 service=checkout order.id=null buckets=1
refund count=1 buckets=0
debug timer present=false
direct count=1 region=null service=checkout
```

The line `work=checkout.internal.heartbeat` appears because the work still runs even when the Observation is disabled. That operation is absent from `completed`. The `Timer` of the same name registered directly afterwards still has `count=1` and the `service` common tag. It lacks `region` because that recording did not pass through an Observation context.

`checkout.debug.cache` appears in `completed`, yet no `Timer` is found. The meter filter affects only the metrics branch. The checkout payment timer has both common labels and one histogram bucket. The refund timer has a measurement count but no histogram buckets in this example. The value `order.id=null` means the high-cardinality key did not become a meter label.

### Choosing Where to Fix When Inspecting the System

- If you need to add information from the request context to an Observation group, use an `ObservationConvention` suited to the instrumented component. For stable shared attributes such as deployment region, use `management.observations.key-values`. Keep high-cardinality identifiers separate from labels used to group metrics.
- If you only need a 300 ms boundary or to change how distributions are computed, configure the corresponding meter. On a web application with Actuator, use the exposed `/actuator/metrics/{name}` endpoint to inspect names, labels, and measurements. If checking exported buckets, read the exporter endpoint, such as `/actuator/prometheus` when a Prometheus registry is present.
- If metrics disappear while traces remain, check meter registration rules and the metrics exporter. If both signals originating from the same Observation disappear, check instrumentation, `ObservationPredicate` conditions, and handlers before changing histogram configuration.

### References

- [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html)
- [Spring Boot 3.3 — Metrics Configuration and Observation Integration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)
- [Micrometer 1.13.0 — DefaultMeterObservationHandler Source](https://github.com/micrometer-metrics/micrometer/blob/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/observation/DefaultMeterObservationHandler.java)