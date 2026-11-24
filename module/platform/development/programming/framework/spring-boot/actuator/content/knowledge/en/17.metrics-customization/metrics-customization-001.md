# Configuring Common Tags with management.metrics.tags and MeterRegistryCustomizer

## 1. What Problem Do Common Tags Solve?

Suppose the same `orders.accepted` metric is collected across multiple services, environments, and deployment regions. Looking only at the metric name, we do not yet know which application the numbers belong to or where it is running.

A **tag** is a key/value pair attached to a meter that helps classify and filter metrics. A **common tag** is a tag configured at the registry level so that meters within that scope receive the same default metadata. For example:

```text
Name: orders.accepted
Common tags:
    application = billing-service
    environment = staging
    region      = ap-southeast-1
Meter-specific tags:
    channel     = web
```

This makes it possible to query "the number of accepted orders for billing-service in staging", or compare deployment regions while keeping the same metric name.

In the Spring Boot Actuator ecosystem:

```text
Deployment configuration source
    -> management.metrics.tags or MeterRegistryCustomizer
    -> configure MeterRegistry before registering meters
    -> meter receives matching tags
    -> Actuator/metrics exporter allows inspection and querying
```

Common tags do not generate events themselves, do not increment counters, and do not alter timer calculations. They change the identifying/classifying metadata of a meter.

## 2. Understanding the Boundaries of a Common Tag

### 2.1. Common Tags and Meter-Specific Tags Complement Each Other

| Information | Appropriate Placement | Reason |
| --- | --- | --- |
| Application name | Common tag | Stable across application metrics |
| Deployment environment | Common tag | Used for filtering local/staging/production |
| Deployment region | Common tag | Shared deployment context of the registry |
| Channel type web/batch | Meter-specific tag if it can differ per event | Reflects a classification dimension of the operation |
| Outcome success/failure | Meter-specific tag | Can differ between events |
| Per-request ID, customer ID, error message | Do not use as common tag | Not stable shared context; easily creates too many series |

A meter is identified primarily by its name and set of tags. The same name with a different `region` or `channel` can be two distinct meters in the registry. Counts do not automatically transfer from one meter to another when tags change.

### 2.2. "Common" Has Registry Scope

Common tags are applied through the configured registry and its corresponding export mechanism. If code creates a registry manually outside the Spring lifecycle, Boot's configuration does not automatically appear on that object.

Do not equate common tags with:

- Parameters or headers of an HTTP request.
- Logging system MDC.
- Tags of a trace/span.
- Labels added by a monitoring server when scraping data.

They may share some concepts such as environment or application, but they are different mechanisms.

## 3. First Approach: management.metrics.tags

Use properties when values can be described via deployment configuration. For example, in a Spring Boot 3.3 application that already has Actuator:

```yaml
spring:
  application:
    name: billing-service

management:
  metrics:
    tags:
      application: "${spring.application.name}"
      environment: "${APP_ENV:local}"
      region: "${DEPLOY_REGION:local}"
```

The keys `application`, `environment`, and `region` are tag names chosen by the application. Setting `spring.application.name` does not mean every meter automatically gets an `application` tag; here we explicitly declare that mapping.

The placeholders mean:

- `${spring.application.name}`: uses the application name from Spring configuration.
- `${APP_ENV:local}`: uses the configured APP_ENV value if present, otherwise `local`.
- `${DEPLOY_REGION:local}`: uses the deployment region, with a default value when running locally.

These tag values should be represented as strings. Do not let environment or region names vary merely due to casing, whitespace, or inconsistent naming conventions.

If using `application.properties`, the equivalent configuration is:

```properties
spring.application.name=billing-service
management.metrics.tags.application=${spring.application.name}
management.metrics.tags.environment=${APP_ENV:local}
management.metrics.tags.region=${DEPLOY_REGION:local}
```

Choose the configuration format suited to the project; there is no need to duplicate the same declarations in both files.

Spring Boot describes this mechanism directly in [Common Tags](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.common-tags). There is no need to rewrite those tags at every `registry.counter(...)` call or every timer builder.

### Profiles and Environment Do Not Automatically Mean the Same Thing

Values can be configured per profile, but profile names are an application technical choice. An application can enable multiple profiles simultaneously, such as `staging,redis`. Therefore, do not assume the profile list itself is the desired environment value for querying.

Define a field such as APP_ENV with a clear convention when operational environment classification is needed. Profile-specific files, environment variables, and startup arguments still follow Spring Boot's configuration property precedence rules.

## 4. Second Approach: MeterRegistryCustomizer

Use `MeterRegistryCustomizer` when you need to pull data from Java configuration, validate/normalize values, or apply customization based on registry type.

### 4.1. Complementary Configuration, No Duplicate Key Declarations

For example, choose to split responsibilities as follows:

- `application` and `environment` belong in properties.
- `region` is added via a customizer.
- Business tags such as `channel` are declared by each meter.

YAML for this approach:

```yaml
spring:
  application:
    name: billing-service

app:
  metrics:
    region: "${DEPLOY_REGION:local}"

management:
  metrics:
    tags:
      application: "${spring.application.name}"
      environment: "${APP_ENV:local}"
```

In this approach, do not also declare `management.metrics.tags.region`, because region already has a single clear owner.

The file `CommonMetricsConfiguration.java`, within the application's component-scan scope:

```java
package demo;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class CommonMetricsConfiguration {
    @Bean
    MeterRegistryCustomizer<MeterRegistry> deploymentRegion(Environment environment) {
        String region = environment.getRequiredProperty("app.metrics.region").trim();
        if (region.isEmpty()) {
            throw new IllegalArgumentException("app.metrics.region must not be blank");
        }
        return registry -> registry.config().commonTags("region", region);
    }
}
```

The factory method produces a configuration callback. The lambda's `registry` parameter is the registry passed in by Boot when applying customizations; there is no need to inject `MeterRegistry` into the factory method just to call it back.

`getRequiredProperty` makes the requirement for region configuration explicit; the example also trims leading/trailing whitespace and rejects empty values. You can add validation against an allowed set of values according to deployment conventions if needed, but avoid querying remote services or reading per-request data inside the registry initialization callback.

Spring Boot documents how to use the callback in [Getting Started with metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#getting-started).

### 4.2. Generic Type Determines Application Scope

`MeterRegistryCustomizer<MeterRegistry>` can apply to compatible registry types managed by Spring. When you only need to customize a specific type, you can declare a concrete generic type, for example `MeterRegistryCustomizer<SimpleMeterRegistry>`.

That has a practical consequence: a customizer targeting SimpleMeterRegistry is not a general configuration guaranteed to appear on another Prometheus registry. Keep the generic type explicit rather than using a raw type; verify the actual registry type in the deployment environment.

Do not create a new registry inside a customizer. The goal is to configure the passed-in object, not to create a separate metrics system.

## 5. Timing of Application Matters More Than Calling commonTags Anywhere

A proper sequence is:

```text
Create registry
    -> apply customizers and related configurations/filters
    -> bind metric groups
    -> register and use business metrics
```

Boot provides the proper lifecycle so customizers run before binding standard meters it manages. In the Spring Boot 3.3.0 source code, `MeterRegistryPostProcessor` applies customizers before the corresponding filters/binders; see [MeterRegistryPostProcessor source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryPostProcessor.java).

This is why you choose a customizer bean instead of waiting until an `ApplicationRunner`, a first request, or an arbitrary initialization method to call `registry.config().commonTags(...)`.

### Late Configuration Does Not Retroactively Update Existing Meters

In Micrometer, common tags are applied through an identifier-mapping mechanism when a meter is registered. When a meter already exists, adding common tags does not mean the old meter object's identifier gets modified.

Moreover, calling the same name and input tags again after the mapping configuration changes can return a **different meter** because the final tag set has changed. The new meter's count can start from 0 while the old meter retains the old count. The experiment later in this lesson verifies this exact case.

Therefore, changing common tags is changing identifier configuration. Design it to be stable across the deployment lifecycle; do not use commonTags as a setter to switch the active environment or user.

## 6. When Keys Collide: Distinguish Two Kinds of "Precedence"

### 6.1. Spring Configuration Source Precedence

If multiple sources provide `management.metrics.tags.environment`, Spring Boot resolves the effective configuration source before that value is used.

For example, a value in a file can be overridden by a higher-precedence source such as a startup argument according to Boot's rules. This is Spring's configuration mechanism; see [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 6.2. Merging Tags When a Meter Is Registered

This is a different step. With Micrometer 1.13.0's common-tag filter mechanism:

- Common tags do not override a tag with the same key already present on the meter ID.
- A later common-tag filter does not override a value for the same key already added by an earlier common-tag filter.
- Calling `commonTags` multiple times can add new keys; it should not be understood as replacing the entire previous tag set.

The rule is documented in [Micrometer 1.13.0 MeterFilter.commonTags](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/config/MeterFilter.java).

For example, if the registry has a default region of `ap-southeast-1`, but a meter is registered with `region=eu-west-1`, the meter-specific tag can be preserved as `eu-west-1`. **Common tags are shared default values, not an enforcement mechanism forcing every meter to carry a single value.**

Do not invent a rule like "YAML always beats Java" or "Java always overrides YAML" for colliding keys. Callbacks, filters, and meter-specific tags form a processing chain; give each key a single owner and verify the final identifier.

### 6.3. What If There Are Multiple Customizers?

If ordering between customizers is needed, Spring's `@Order`/`Ordered` mechanism can be used; higher-priority customizers are applied earlier in Boot's lifecycle. However, callback order is not the display order of labels on every monitoring system.

In particular, Boot documentation notes that common tag order matters for Graphite and recommends a custom MeterFilter when controlling it that way is necessary. Do not rely on YAML line order or the label string order seen on screen when designing identifiers.

## 7. Standalone Experiment with Boot's Real Metrics Configuration

The following program uses a Spring context and imports Boot's actual metrics auto-configurations. It does not start a web server. Configuration is placed into the Environment before refreshing the context to verify both `management.metrics.tags` binding and the customizer.

Fixed values are chosen to make results reproducible; this is not a mandatory configuration for every application.

### 7.1. Gradle Project

Use JDK 17 or higher; JDK 21 is recommended. Create a separate project with `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-actuator-autoconfigure'
    implementation 'org.springframework:spring-context'
    implementation 'io.micrometer:micrometer-core'
}

application {
    mainClass = 'demo.CommonTagsDemo'
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
rootProject.name = 'common-tags-demo'
```

The Spring Boot 3.3.0 BOM manages the library versions used in the experiment, including Micrometer 1.13.0. In a Boot project that already has dependency management, simply add Actuator if not already present:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

You do not need to add the AOP starter just to use common tags.

### 7.2. Complete Java Program

File `src/main/java/demo/CommonTagsDemo.java`:

```java
package demo;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.boot.actuate.autoconfigure.metrics.MetricsAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.metrics.export.simple.SimpleMetricsExportAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

public class CommonTagsDemo {
    @Configuration(proxyBeanMethods = false)
    @ImportAutoConfiguration({
        MetricsAutoConfiguration.class,
        SimpleMetricsExportAutoConfiguration.class
    })
    public static class Config {
        @Bean
        MeterRegistryCustomizer<MeterRegistry> regionTags(Environment environment) {
            String region = environment.getRequiredProperty("app.metrics.region");
            return registry -> registry.config().commonTags("region", region);
        }

        @Bean
        MeterBinder demoOrders() {
            return registry -> registry.counter("demo.orders.accepted", "channel", "web")
                    .increment(2);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo", Map.of(
                            "spring.application.name", "billing-demo",
                            "management.metrics.tags.application", "${spring.application.name}",
                            "management.metrics.tags.environment", "staging",
                            "management.metrics.use-global-registry", "false",
                            "app.metrics.region", "ap-southeast-1"
                    )));
            context.register(Config.class);
            context.refresh();

            SimpleMeterRegistry registry = context.getBean(SimpleMeterRegistry.class);
            Counter inherited = registry.get("demo.orders.accepted")
                    .tag("region", "ap-southeast-1").counter();
            System.out.println("boot.tags=" + tags(inherited));
            System.out.printf(Locale.ROOT, "boot.count=%.0f%n", inherited.count());

            Counter explicit = registry.counter("demo.orders.accepted",
                    "channel", "web", "region", "eu-west-1");
            explicit.increment();
            System.out.println("explicit.region=" + explicit.getId().getTag("region"));
            System.out.println("distinct.meter=" + (inherited != explicit));
            System.out.printf(Locale.ROOT, "boot.original.count=%.0f%n", inherited.count());
        }

        demonstrateLateConfiguration();
    }

    private static void demonstrateLateConfiguration() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            Counter before = registry.counter("demo.late", "phase", "before");
            before.increment(3);
            registry.config().commonTags("region", "local");
            registry.config().commonTags("region", "replacement", "team", "training");

            Counter after = registry.counter("demo.late", "phase", "after");
            Counter requestedAgain = registry.counter("demo.late", "phase", "before");

            System.out.println("late.before.region=" + before.getId().getTag("region"));
            System.out.println("late.after.region=" + after.getId().getTag("region"));
            System.out.println("late.after.team=" + after.getId().getTag("team"));
            System.out.println("late.reused.instance=" + (before == requestedAgain));
            System.out.printf(Locale.ROOT, "late.old.count=%.0f late.new.count=%.0f%n",
                    before.count(), requestedAgain.count());
        } finally {
            registry.close();
        }
    }

    private static Map<String, String> tags(Meter meter) {
        Map<String, String> result = new TreeMap<>();
        meter.getId().getTags().forEach(tag -> result.put(tag.getKey(), tag.getValue()));
        return result;
    }
}
```

The `MeterBinder` in the experiment simply registers a counter to provide data for comparison. It is invoked by Boot after the registry configuration step; there is no need to add an endpoint or repeat the application/environment/region tags in the binder.

Run with an installed Gradle, or the experiment project's own wrapper:

```shell
gradle -q run
```

To compile/run directly, first run `gradle -q copyRuntimeDependencies`, then use the commands on Windows:

```shell
javac --release 17 -encoding UTF-8 -parameters -cp "build/runtime-libs/*" -d build/manual-classes src/main/java/demo/CommonTagsDemo.java
java -cp "build/manual-classes;build/runtime-libs/*" demo.CommonTagsDemo
```

On Linux/macOS, replace the `;` separating classpath entries in the `java` command with `:`.

### 7.3. Verified Stdout

```text
boot.tags={application=billing-demo, channel=web, environment=staging, region=ap-southeast-1}
boot.count=2
explicit.region=eu-west-1
distinct.meter=true
boot.original.count=2
late.before.region=null
late.after.region=local
late.after.team=training
late.reused.instance=false
late.old.count=3 late.new.count=0
```

The intentionally late configuration section may also emit a warning log about configuring a MeterFilter after meters already exist. That log is separate from the stdout lines listed above and is precisely the sign of improper configuration ordering in the second half of the experiment.

`TreeMap` is only used to print tags in a stable order to make comparing results easier. It does not define the tag order when exporting to a backend.

## 8. Explaining the Experiment Results

### 8.1. Tags from Properties and Customizer Are Combined

The `boot.tags` line has four keys:

| Key | Value | Source |
| --- | --- | --- |
| application | billing-demo | management.metrics.tags and spring.application.name placeholder |
| environment | staging | management.metrics.tags.environment |
| region | ap-southeast-1 | MeterRegistryCustomizer |
| channel | web | Meter-specific tag when binder registers counter |

The counter has a count of 2 because the binder called `increment(2)`. Adding tags does not make the count four or increase it with the number of keys.

In Boot 3.3.0 source code, `management.metrics.tags` is converted into a filter that applies common tags via [PropertiesMeterFilter](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/PropertiesMeterFilter.java). Thus, properties and Java enter the same meter-identifier configuration process, rather than creating two independent counter copies just because there are two configuration sources.

### 8.2. A Meter-Specific Tag Creates a Different Identifier

The next registration explicitly specifies `region=eu-west-1`. It keeps that specific value and receives a different meter:

```text
explicit.region=eu-west-1
distinct.meter=true
boot.original.count=2
```

The new counter is incremented once; the original counter remains 2. If querying across all regions aggregated for the same metric name, understand that you are summing metrics from distinct series.

Being able to set a meter-specific region also shows why key semantics must be consistent: if region is defined by convention as "where the application is deployed", business code should not reuse the same key to mean "the customer region being served". When both are needed, choose two clearly distinct tag names.

### 8.3. Common Tags Added Later Do Not Modify Existing Meters

The first meter of the second registry was registered before any common tags existed:

```text
late.before.region=null
```

The `null` value here means **the region key is absent from the ID**, not a tag with the string value `"null"`.

After two commonTags calls, the newly registered meter has:

```text
region = local
team   = training
```

Region stays `local`, because the second commonTags call does not override the region already added by the earlier common-tag filter. The missing team key is added.

Finally, requesting to register the same name and input tag `phase=before` again goes through the current configuration and receives an ID with the added common tags. It does not reuse the old instance:

```text
late.reused.instance=false
late.old.count=3 late.new.count=0
```

This explains why adding tags late can produce split data: an older portion of the metric lacks the tags, a newer portion has the tags, and counts are not automatically migrated.

## 9. Verifying Results in a Real Application

### 9.1. Inspecting the Registry Used by the Application

For a registered meter, you can read `getId().getTags()` to inspect tags on a specific object, as the experiment did. When there are multiple registries or a CompositeMeterRegistry, identify which child registry actually exports data; do not draw conclusions about final exported data solely from a registry object that the backend does not use.

Prefer injecting the Spring-managed `MeterRegistry`. A `new SimpleMeterRegistry()` created manually in a service is a different object; customizer beans do not automatically run on every Java object created with new.

Static methods on `Metrics` use the global registry. Boot integrates with the global registry depending on configuration, but you should not rely on the assumption that every static registration path is equivalent to the injected bean. The experiment sets `management.metrics.use-global-registry=false` to avoid affecting global state across runs.

### 9.2. Inspecting via Actuator

In a Boot web application that already has Actuator, you can expose the metrics endpoint for local configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

After the application has registered the corresponding metric:

```shell
curl "http://localhost:8080/actuator/metrics/demo.orders.accepted"
curl "http://localhost:8080/actuator/metrics/demo.orders.accepted?tag=environment:staging&tag=region:ap-southeast-1"
```

The requests above apply to a web application with the same metric; the console program in the previous section does not open those URLs itself. Port, base path, and authentication requirements depend on the application's configuration.

Check the available tags and filter by verified values. Do not treat a fixed JSON output from one registry as a rigid template for every backend. If there is mapping in a child registry/exporter, check against the actual exported data before concluding a tag is missing.

### 9.3. Inspecting in the Monitoring System

With Prometheus, tags typically become labels. Metric names may be converted according to a naming convention; for instance, a counter may be exported as `demo_orders_accepted_total`; verify the actual name before writing queries.

The example query applies only after the Prometheus registry is configured, data has been scraped, and these names/labels actually exist:

```promql
sum by (region) (
  rate(demo_orders_accepted_total{
    application="billing-demo",
    environment="staging"
  }[5m])
)
```

Common tags let you keep the application/environment scope fixed and then compare regions. They do not set up scraping or data transport themselves; the console program using SimpleMeterRegistry does not include this Prometheus export step.

## 10. Keeping the Tag Set Useful and Stable

### 10.1. Watch the Number of Value Combinations

A time series is typically tied to a specific set of labels. If a metric has 2 environments, 3 regions, and 4 channels across the entire system, there can be up to 24 combinations across those dimensions, before considering other dimensions.

That is the number of potential combinations across system-wide data, not that every process creates 24 meters by default: environment/region are typically fixed per process; only combinations that are actually created appear.

Stable common tags like application/environment/region generally have clear analytical value. Tags taken from request IDs or individual customers can grow unboundedly with data. Do not use common tags to carry information that changes per request; use finite classification groups on appropriate metrics, or other detailed tracing tools.

Micrometer's [Naming Meters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html) documentation explains common tags, when they apply, and tag cardinality risks.

### 10.2. Renaming Tags or Changing Values Changes Historical Classification

Switching environment from `prod` to `production` creates a different label value. Dashboards filtering on `prod` do not automatically read `production` as well. Similarly, renaming the `application` key to `service` affects queries and data conventions.

When changing configuration, update related queries and plan for a transition period where old and new metrics coexist. Do not expect commonTags to rewrite already-exported historical data.

### 10.3. Do Not Use Common Tags to Carry Mutable State

Deployment region is suitable as a common tag when stable across the process lifetime. Conversely, order status, processing outcome, or current user can change between events. If a per-request value is read in a customizer at startup, it will not automatically update on subsequent requests.

A registry configuration callback is an initialization step, not a listener for every business state change.

## 11. Common Mistakes and How to Fix Them

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| spring.application.name is set but application tag is missing | Corresponding tag not declared | Add management.metrics.tags.application or an explicit customizer |
| Only some metrics have tags | Configured after old metrics were registered, or multiple registries exist | Move configuration to initialization and check the exporting registry |
| Customizer does not run | Configuration outside component-scan scope, bean not registered, or generic type mismatch | Check bean registration and actual registry type |
| Tag does not have expected value | Different effective configuration, placeholder issue, or conflicting key ownership | Verify configuration sources and inspect the final ID |
| Calling commonTags again does not change old value | Treating commonTags as an overwrite operation | Configure once and avoid multiple owners for the same key |
| Same metric name has split counts | Different final tags, new meter created after config change | Inspect the full tag set and stabilize identity from startup |
| Self-created registry has data but Actuator does not see it | Recording into a registry outside Spring management | Use the injected registry |
| Values differ only by whitespace/casing | Missing convention or normalization | Validate/normalize in configuration or customizer |
| Series count grows rapidly | Tag has too many values or changes per event | Limit classification dimensions and remove unsuitable fields |

## 12. Hands-On Verification Exercises

1. **Properties only:** remove the region customizer and move region to management.metrics.tags.region. With a fresh context, confirm the counter has all four tags: application/environment/region/channel.
2. **Split across two sources:** keep application/environment in properties and region in the customizer as in the experiment. Identify the owner of each key.
3. **Check late configuration:** explain why the earlier meter has region=null and count 3, while the re-registered meter has count 0. State how to structure initialization to avoid this.
4. **Check key collision:** register a meter with a meter-specific region; confirm common tags do not force the deployment value. Propose separate names if measuring both deployment region and served region is needed.
5. **Check registry type:** replace the generic customizer with a specific type and evaluate which registries it will affect before switching to another backend.

After this practice, you should be able to trace the source of each tag, when it is applied, and which registry actually exports it. Those three pieces of information help you choose between properties and customizers while avoiding metric series with missing tags or unintended splits.
