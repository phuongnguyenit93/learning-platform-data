# Configuring Common Key-Values and Enabling or Disabling Observation Groups

## 1. Problem: One Application, Many Measurements

Suppose a checkout service has operations `checkout.calculate`, `checkout.audit.persist`, and `checkout.audit.preview`. When inspecting monitoring data, we want to answer two questions:

- Which service, environment, and region does this measurement come from?
- In the current environment, which operation groups should be observed?

**Common key-values** solve the first question with shared key–value pairs. **Observation enable/disable configuration** solves the second question with policies by observation name.

An observation is an event observing an operation together with its lifecycle and context. `ObservationRegistry` holds observation handlers; `MeterRegistry` holds meters such as timers and counters. The two registries have distinct responsibilities.

In this lesson, an "observation group" means names sharing a common prefix branch, such as `checkout.audit`. This is a naming organization for applying policies; it is not a special bean type, health group, or Actuator endpoint group.

The hands-on exercise uses Spring Boot **3.3.0**, Micrometer **1.13.0**, and Java code compatible with **Java 17 or newer**. The example was compiled with `javac --release 17` and run on JDK 21. The results below tie to the example's configuration and versions.

## 2. Two Property Groups to Distinguish

| Property | Question solved | Example |
| --- | --- | --- |
| `management.observations.key-values.<key>` | Which common info should be attached to observations? | `region=vn-south` |
| `management.observations.enable.<name>` | Which observation names/branches are allowed? | `checkout.audit=false` |

Spring Boot binds configuration under `management.observations` into `ObservationProperties`. `key-values` is a string-to-string map; `enable` is a string-to-boolean map. [ObservationProperties Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationProperties.html).

### 2.1. Common Key-Values Are Low-Cardinality Tags

Configuration in `application.properties`:

~~~properties
spring.application.name=checkout-demo

management.observations.key-values.service=${spring.application.name}
management.observations.key-values.region=vn-south
management.observations.key-values.environment=lab
~~~

Meaning in the example:

- `service` takes the value `checkout-demo` from the application name property.
- `region` distinguishes the deployment region.
- `environment` distinguishes the runtime environment.

The tag name `service` is our choice; `spring.application.name` on its own does not automatically mean every meter has a `service` tag. It is the `management.observations.key-values.service` line that creates that link in the example.

Spring Boot adds these pairs as key–values with a small number of distinct values, called **low cardinality**. They can become metric tags and trace attributes when the corresponding handlers are configured. [Spring Boot 3.3: Common Tags](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html#actuator.observability.common-tags).

Common tags should describe the application or environment and stay stable while running. Do not put `orderId`, `requestId`, email, token, or URLs containing identifiers into common tag configuration. A normal-looking tag name still causes time-series explosion if its value changes per request.

Design example: with 2 regions, 3 environments, and 2 transaction channels, one metric name can split into up to `2 × 3 × 2 = 12` tag combinations if every combination occurs. Adding 100,000 order IDs can make the combination count grow huge. That is why you must control the value set, not just the number of keys. [Micrometer: Naming Meters and Tags](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Per-operation values are still declared where the observation is created, such as `channel=web`. Common values and per-operation values should use distinct keys. Avoid using common tags to compete with keys such as `error`, `status`, or `method` that specific instrumentation provides.

### 2.2. The Scope of "Common" Has Limits

These properties apply through the Spring Boot-configured registry. If you call `ObservationRegistry.create()` yourself and use that standalone registry, you do not automatically receive policies from `application.properties`. Inject the Spring-managed `ObservationRegistry` into application code.

Nor should you assume a meter created directly via `Counter.builder(...)` or `Timer.builder(...)` will receive tags from `management.observations.key-values`. That meter might not go through an observation. To attach common tags at the metric layer, see `management.metrics.tags.<key>` or `MeterRegistryCustomizer`. [Spring Boot 3.3: Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Example distinguishing the two intents:

~~~properties
# Common observation tag:
management.observations.key-values.region=vn-south

# Common metric-layer tag:
management.metrics.tags.environment=lab
~~~

There is no need to configure both lines mechanically for the same goal. First decide whether the data needs to appear at the observation layer, the metric layer, or both.

## 3. Enabling/Disabling by Name and Name Branch

Illustrative policy for this lesson:

~~~properties
management.observations.enable.all=false
management.observations.enable.checkout=true
management.observations.enable.checkout.audit=false
management.observations.enable.checkout.audit.preview=true
~~~

We want disabled by default, the `checkout` branch enabled, the `checkout.audit` sub-branch disabled, yet the narrower `checkout.audit.preview` branch re-enabled.

### 3.1. Lookup Rules in Spring Boot 3.3.0

For the name `checkout.audit.preview`, the implementation checks in order:

~~~text
checkout.audit.preview
checkout.audit
checkout
all
default value true if no matching configuration exists
~~~

**The most specific configuration found determines the outcome of the property policy.** Line order in the file does not override name specificity.

For a longer name `checkout.audit.preview.render`, the first lookup is the full name, then segments after dots are stripped one by one from the end. Thus it can inherit configuration from `checkout.audit.preview`.

An important point verified in the example: lookup operates on dot-separated segments. `checkout.auditExtra` does not inherit `checkout.audit=false`; it looks up `checkout.auditExtra`, then `checkout`. Do not treat `enable` as arbitrary substring matching.

| Observation name | Most specific matching config | Result |
| --- | --- | --- |
| `checkout.calculate` | `checkout=true` | Enabled |
| `checkout.audit.persist` | `checkout.audit=false` | Disabled |
| `checkout.audit.preview` | `checkout.audit.preview=true` | Enabled |
| `checkout.auditExtra` | `checkout=true` | Enabled |
| `shipping.quote` | `all=false` | Disabled |

This table will be checked with a live runnable program in Section 5.

### 3.2. Defaults and Common Patterns

If `enable` is not configured, the property policy allows observations by default. However, "allowing" does not create measurement points or install missing handlers on its own.

Disable one branch while keeping other names at default:

~~~properties
management.observations.enable.checkout.audit=false
~~~

Disable by default, enable selected branches:

~~~properties
management.observations.enable.all=false
management.observations.enable.checkout=true
~~~

`all` is a special fallback key. `all=true` does not beat a specific entry like `checkout.audit=false`. To re-enable that branch, edit that branch's setting or add a more specific child entry.

Do not write `checkout.*` intending to use a wildcard. This map is neither regular expressions nor glob syntax. Use `checkout` to control the branch, and name business operations consistently from the start.

For library-generated observations, you must use the library's actual observation name. For example, Spring Boot documentation uses `management.observations.enable.spring.security=false` to prevent Spring Security observations. [Spring Boot 3.3: Preventing Observations](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html#actuator.observability.preventing-observations).

### 3.3. Equivalent YAML Notation

Keys containing dots can be written explicitly as map keys:

~~~yaml
management:
  observations:
    key-values:
      service: "${spring.application.name}"
      region: "vn-south"
      environment: "lab"
    enable:
      all: false
      checkout: true
      "checkout.audit": false
      "checkout.audit.preview": true
~~~

This is an equivalent configuration alternative to the `management.observations` section in the properties file, not a second policy to apply on top. Use boolean `true`/`false` for `enable`, and keep tag values as strings.

## 4. Where Does the Policy Act in the Lifecycle?

You can picture the processing flow like this:

~~~text
Application or library code starts an operation
        |
        v
Create observation with name and context
        |
        v
ObservationPredicates decide whether to observe
        |
        +-- reject --> NOOP observation --> business code still runs
        |
        +-- accept --> start --> run business code --> stop
                                                   |
                                                   v
                                         ObservationFilter updates context
                                                   |
                                                   v
                                         handler processes onStop
~~~

`NOOP` is an object that performs no observation work. It is not a command to cancel business logic. With `observation.observe(action)`, `action` still runs even when the observation is rejected.

In Micrometer, `ObservationPredicate` decides whether to use a real observation or a NOOP version; `ObservationFilter` can update the context before `onStop` calls. Therefore, do not rely on a common tag added via filter to assume that tag already exists when predicates or `onStart` run. [Micrometer: Observation Components](https://docs.micrometer.io/micrometer/reference/1.13/observation/components.html).

If filtering requires context types or conditions more complex than names, you can register an `ObservationPredicate` bean. A `true` decision from properties does not force other predicates to accept. When environment-based conditions are needed, read environment config directly rather than waiting for tags attached at the end of the lifecycle.

Disabling an observation also does not mean all overhead before the observation point disappears. Code already executed prior to calling the observation API, business code, and independent instrumentation still run along their paths.

## 5. Hands-On: Verifying Common Tags and Group Policies

This example is a CLI application, opening no HTTP server and requiring no Prometheus, Zipkin, or external monitoring system. We read timers directly from `MeterRegistry` to separate **whether a measurement exists** from **where measurements are exported**.

### 5.1. Structure and Dependencies

Create an isolated practice directory:

~~~text
observation-policy-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── example/
        │       └── ObservationPolicyDemo.java
        └── resources/
            └── application.properties
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
    <artifactId>observation-policy-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Do not declare a separate Micrometer version in this example; use the versions managed by Spring Boot to keep dependencies consistent.

### 5.2. Complete Configuration

Contents of `src/main/resources/application.properties`:

~~~properties
spring.application.name=checkout-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=OFF

management.observations.key-values.service=${spring.application.name}
management.observations.key-values.region=vn-south
management.observations.key-values.environment=lab

management.observations.enable.all=false
management.observations.enable.checkout=true
management.observations.enable.checkout.audit=false
management.observations.enable.checkout.audit.preview=true
~~~

Banner and background logging are turned off so business stdout is easy to verify. Observation policies live in the `management.observations` lines; logging lines do not decide whether observations are created.

### 5.3. Complete Java Program

Contents of `src/main/java/example/ObservationPolicyDemo.java`:

~~~java
package example;

import java.util.List;
import java.util.TreeMap;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ObservationPolicyDemo {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ObservationPolicyDemo.class, args)) {
            ObservationRegistry observations = context.getBean(ObservationRegistry.class);
            MeterRegistry meters = context.getBean(MeterRegistry.class);
            List<String> names = List.of(
                    "checkout.calculate",
                    "checkout.audit.persist",
                    "checkout.audit.preview",
                    "checkout.auditExtra",
                    "shipping.quote");
            for (String name : names) {
                Observation observation = Observation.createNotStarted(name, observations)
                        .lowCardinalityKeyValue("channel", "web");
                System.out.println("BEGIN " + name + " noop=" + observation.isNoop());
                observation.observe(() -> System.out.println("WORK " + name));
                Timer timer = meters.find(name).timer();
                System.out.println("METER " + name + " count="
                        + (timer == null ? 0 : timer.count()));
                if (timer != null) {
                    TreeMap<String, String> tags = new TreeMap<>();
                    timer.getId().getTags().forEach(tag ->
                            tags.put(tag.getKey(), tag.getValue()));
                    System.out.println("TAGS " + name + " " + tags);
                }
            }
        }
    }
}
~~~

Key points to read in the code:

1. Obtain both registries from the application context to use Spring Boot configuration.
2. `channel=web` is the per-operation tag in the example; the three environment tags come from common configuration.
3. `observe(...)` manages the synchronous operation's lifecycle. Once the inner function finishes, the timer can be read after the observation stops.
4. `isNoop()` helps distinguish a decision at the observation layer from simply missing a meter.
5. `TreeMap` prints tags in deterministic key order without guessing the order returned by the registry.
6. `try-with-resources` closes the application context when finished.

The expression `timer == null ? 0 : timer.count()` is only this example's printing convention. `count=0` on a blocked operation does not prove a real timer exists with count 0; that branch may not find any timer.

### 5.4. Compiling and Running

In the directory containing `pom.xml`, with JDK 17 or newer and Maven:

~~~shell
mvn -q -DskipTests package
java -jar target/observation-policy-demo-1.0.0.jar
~~~

Maven compiles the code and the Spring Boot Maven Plugin packages the executable JAR. The first run requires access to dependency repositories if not already cached locally.

If you want to see the `javac` step explicitly, you can use the following direct run **instead of** the packaging step above. Example commands for PowerShell/Windows:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out src/main/java/example/ObservationPolicyDemo.java
java -cp "out;src/main/resources;lib/*" example.ObservationPolicyDemo
~~~

On Linux/macOS, create `out` with `mkdir -p out` and replace the `;` classpath separator with `:` in the `java` command. Do not run the Java file standalone without providing the Spring Boot/Micrometer libraries.

### 5.5. Stdout of the Baseline Configuration

Lines printed by the program:

~~~text
BEGIN checkout.calculate noop=false
WORK checkout.calculate
METER checkout.calculate count=1
TAGS checkout.calculate {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
BEGIN checkout.audit.persist noop=true
WORK checkout.audit.persist
METER checkout.audit.persist count=0
BEGIN checkout.audit.preview noop=false
WORK checkout.audit.preview
METER checkout.audit.preview count=1
TAGS checkout.audit.preview {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
BEGIN checkout.auditExtra noop=false
WORK checkout.auditExtra
METER checkout.auditExtra count=1
TAGS checkout.auditExtra {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
BEGIN shipping.quote noop=true
WORK shipping.quote
METER shipping.quote count=0
~~~

Comparing the results:

- `checkout.calculate` has a timer with all three common tags plus the local `channel` tag.
- `checkout.audit.persist` is rejected for observation yet still prints `WORK`.
- `checkout.audit.preview` is re-enabled by the more specific configuration.
- `checkout.auditExtra` is enabled by `checkout=true`, confirming segment-boundary lookup.
- `shipping.quote` has no specific rule so it inherits `all=false`.
- `error=none` is supplied by the metric recording mechanism on a successful run; it is not a common tag we declared.

The program installs no tracing bridge or trace exporter. The `TAGS` lines verify timer tags, not proof that traces were sent to an external system.

## 6. Two Tests to Avoid Misunderstanding the Toggles

### 6.1. Re-enabling the Entire Audit Group

Run a new process:

~~~shell
java -jar target/observation-policy-demo-1.0.0.jar --management.observations.enable.checkout.audit=true
~~~

The lines corresponding to `checkout.audit.persist` become:

~~~text
BEGIN checkout.audit.persist noop=false
WORK checkout.audit.persist
METER checkout.audit.persist count=1
TAGS checkout.audit.persist {channel=web, environment=lab, error=none, region=vn-south, service=checkout-demo}
~~~

`checkout.audit.preview` remains enabled. `shipping.quote` remains disabled due to `all=false`.

These are two separate precedence layers: the command-line argument overrides `checkout.audit` from the file; then the name-based policy still looks up the most specific key. An argument setting `all=true` does not delete other specific keys in the map. Configuration source precedence and branch selection must be evaluated separately. [Spring Boot 3.3: Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 6.2. Disabling Only the Metric While Keeping the Observation

Re-run the baseline configuration in a new process, adding only the metric toggle:

~~~shell
java -jar target/observation-policy-demo-1.0.0.jar --management.metrics.enable.checkout.calculate=false
~~~

Corresponding stdout excerpt:

~~~text
BEGIN checkout.calculate noop=false
WORK checkout.calculate
METER checkout.calculate count=0
~~~

`noop=false` indicates the observation was still created. The meter filtering mechanism prevented the timer from being registered, so there is no `TAGS` line for that timer. This is why you should not use "metric missing" alone to conclude that the observation was disabled. [Micrometer: Meter Filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Both tests use a fresh process to avoid old meters remaining in the registry and making the output hard to read.

## 7. Distinguishing Observation, Metric, Trace, and Endpoint

| Need | Suitable mechanism | Scope to understand |
| --- | --- | --- |
| Block observing a group of operations | `management.observations.enable.<name>=false` | Blocks the observation and outputs produced by its handlers |
| Block a group of metrics | `management.metrics.enable.<name>=false` | Filters at the meter layer; the observation may still exist |
| Attach common tags to observations | `management.observations.key-values.<key>` | Flows through the registry and observation handling |
| Attach common tags to metrics | `management.metrics.tags.<key>` | Flows through metric configuration |
| Allow HTTP clients to reach Actuator endpoints | `management.endpoints.web.exposure.include` | Controls endpoint exposure, does not alter observation policy |
| Adjust trace sampling rate | `management.tracing.sampling.probability` | Controls trace sampling, does not replace name-based observation policy |

Observation is a connection point that can produce metrics and spans when matching handlers exist. Blocking that observation stops handlers from processing its lifecycle. However, directly recorded meters, independently created spans, or data collected by another agent may still exist.

Conversely, filtering metrics alone does not turn off tracing. When adding Micrometer Tracing to an application, you must configure the appropriate tracer/bridge and trace exporter; the Actuator starter in the example does not prove the entire trace pipeline is in place. [Spring Boot 3.3: Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

A trace sampling rate of 0 does not mean business code stops running or all metrics vanish. Do not use tracing switches to replace enabling/disabling observations by group.

## 8. Common Mistakes and How to Diagnose Them

| Symptom or configuration | Possible cause | How to check/fix |
| --- | --- | --- |
| `management.observation...` has no effect | Wrong branch name; missing `s` | Use exact `management.observations` |
| `enable.checkout.*=false` does not block group as expected | Mistakenly assuming wildcard support | Use the `checkout` key and consistent segmented names |
| `all=false` yet observations still appear | A specific branch is enabled | List the lookup chain for that exact name |
| Disabled `checkout.audit` yet `checkout.auditExtra` stays enabled | The two names are not on the same segment branch | Compare against the example's table and stdout |
| `enable...=true` yet no data appears | Missing instrumentation/handler, wrong registry, or rejected by another predicate | Check where the observation is created and which registry is injected |
| Common tags missing when checked at start of operation | Checked before the filter stage adds tags | Inspect context at `onStop` or timers after stopping |
| No metric seen and concluding observation is disabled | May just be meter-filtered or not yet exported | Check observation, registry, and exporter separately |
| Disabled observation yet business logic still runs | Normal NOOP behavior | Use a separate business mechanism if wanting to stop functionality |
| Edited config file while JVM is running and expected instant change | No auto-reload mechanism configured | Restart to verify the new configuration |

A useful diagnostic sequence is: identify the **actual observation name**, check the **effective configuration values**, inspect the **NOOP decision**, and then inspect **meters/spans and export destinations**. Following this chain reveals whether the issue is in policy, instrumentation, or the export pipeline.

Do not rename observations to order IDs or URIs containing identifiers just to find a single transaction easily. Keep names representing the operation type, such as `checkout.calculate`; place specific data into the appropriate context with cardinality and privacy controls.

Do not use observation policies as security controls or feature flags. Decisions to allow payments, record business audits, or permit API access must be enforced by their corresponding logic and policies.

## 9. Self-Verification Exercises

Apply each change independently on the baseline configuration and restart:

1. Change `region` to `vn-north`. Created timers must carry the new region tag; the list of allowed operations stays unchanged.
2. Change `checkout.audit.preview` to `false`. Both `checkout.audit.persist` and `checkout.audit.preview` must have `noop=true` yet still print `WORK`.
3. Keep `checkout.audit=false` and add `checkout.audit.persist=true`. Only `persist` is re-enabled within the audit branch under this change.
4. Change `all=true` while keeping the other specific keys from the baseline configuration. `shipping.quote` becomes enabled, while `checkout.audit.persist` remains disabled.
5. Disable the `checkout.calculate` metric as in Section 6.2. Explain why `noop=false` goes together with `count=0`.
6. Remove the `management.observations.key-values.service` line. Observe that the application name is still `checkout-demo` yet timers no longer receive the `service` tag from this common configuration.

After these experiments, learners should be able to explain three relationships: the name determines the policy branch; key-values describe observation data; handlers and registries determine how data is recorded as metrics/traces.
