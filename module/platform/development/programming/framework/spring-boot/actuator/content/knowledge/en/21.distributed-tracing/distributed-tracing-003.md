# Choosing the OpenTelemetry or Brave Bridge and Compatible Exporters

## 1. Which Components Need to Be Chosen?

A service may create observations without yet sending distributed tracing data. To pick the right dependencies, you first need to see the data path:

~~~text
Application / framework code
        |
        v
Micrometer Observation and Micrometer Tracing
        |
        v
Bridge: OpenTelemetry or Brave
        |
        v
Corresponding tracer implementation
        |
        v
Exporter / reporter and transport mechanism
        |
        v
Collector or trace storage and search backend
~~~

A **trace** is the record of an execution flow that can span multiple services. A **span** represents a unit of work within that trace. A **tracer** creates and manages spans along with trace context.

A **bridge** is the adapter layer between the Micrometer Tracing API and the chosen tracing library. An **exporter/reporter** is responsible for sending recorded spans out in an appropriate format and protocol. A **backend** is the system that stores and allows querying data; a **collector** can receive, process, and forward data to a backend.

Examples:

~~~text
Micrometer → OpenTelemetry bridge → OpenTelemetry SDK → OTLP → Collector
Micrometer → Brave bridge         → Brave             → Zipkin API → Zipkin
Micrometer → OpenTelemetry bridge → OpenTelemetry SDK → Zipkin API → Zipkin
~~~

The third line shows that the tracer library name does not hardcode which backend must be used. OpenTelemetry can export to Zipkin; seeing Zipkin does not force you to choose Brave.

This lesson focuses on **Micrometer Tracing integration managed by Spring Boot 3.3**. That is one specific integration path; do not mix its configuration with the OpenTelemetry Java Agent or another OpenTelemetry starter suite and treat them as the same mechanism.

## 2. Choose Exactly One Bridge

Micrometer Tracing supports two primary bridges:

| Tracer Implementation | Bridge Dependency |
| --- | --- |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` |
| OpenZipkin Brave | `io.micrometer:micrometer-tracing-bridge-brave` |

**Place only one bridge on the runtime classpath.** Micrometer instructs not to include both bridges at the same time. [Micrometer Tracing: Supported Tracers](https://docs.micrometer.io/tracing/reference/tracers.html).

Design rationale: the application needs one translation path from the common tracing API to the chosen implementation. Adding two bridges is not an automatic fallback mechanism, nor is it a valid way to "use Brave in part and OpenTelemetry in part" in a standard configuration.

When both are accidentally present, configuration behavior can depend on beans, auto-configuration conditions, and actual dependencies. Do not rely on the application still starting up to conclude that both are cooperating properly.

Similarly, having only a bridge does not prove data is being sent to a storage backend. You also need to check the exporter/reporter, endpoint, sampling, and receiver.

If you need to send data to multiple destinations, design an explicit export path, such as forwarding through a Collector. Do not add a second bridge as a substitute for designing multiple destinations.

## 3. Combinations Supported by Spring Boot 3.3

Every combination in the table below requires `org.springframework.boot:spring-boot-starter-actuator` alongside the listed dependencies.

| Chosen Tracer | Bridge | Exporter/Reporter | Data Ingestion Path |
| --- | --- | --- | --- |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` | `io.opentelemetry:opentelemetry-exporter-otlp` | Collector/backend with an appropriate OTLP receiver port |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` | `io.opentelemetry:opentelemetry-exporter-zipkin` | Zipkin API |
| OpenTelemetry | `io.micrometer:micrometer-tracing-bridge-otel` | `io.micrometer:micrometer-tracing-reporter-wavefront` | Wavefront |
| Brave | `io.micrometer:micrometer-tracing-bridge-brave` | `io.zipkin.reporter2:zipkin-reporter-brave` | Zipkin API |
| Brave | `io.micrometer:micrometer-tracing-bridge-brave` | `io.micrometer:micrometer-tracing-reporter-wavefront` | Wavefront |

These are the combinations documented by Spring Boot 3.3, not a table claiming every Java exporter can be paired with every tracer. [Spring Boot 3.3: Tracer Implementations](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.tracing.implementations).

### 3.1. Commonly Mismatched Combinations

- `micrometer-tracing-bridge-brave` with `opentelemetry-exporter-otlp` does not produce a direct OTLP export path auto-configured by Spring Boot 3.3.
- `micrometer-tracing-bridge-otel` with `zipkin-reporter-brave` is not a drop-in replacement for the OpenTelemetry Zipkin exporter.
- `opentelemetry-exporter-zipkin` and `opentelemetry-exporter-otlp` both belong to the OpenTelemetry ecosystem, yet they use different formats and ingestion endpoints.
- Adding an API-only dependency does not guarantee a complete runtime implementation and export mechanism.

For OTLP specifically, Spring Boot 3.3 only auto-configures it with OpenTelemetry. [OtlpAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpAutoConfiguration.html).

### 3.2. Note on Wavefront in the Table

Wavefront is kept in the table to reflect Spring Boot 3.3's integration scope. Micrometer documentation currently marks the Wavefront reporter as deprecated due to the service's end-of-life announcement. Therefore, do not treat its presence in this version's historical table as a recommendation for choosing a new target backend. [Micrometer Tracing: Supported Reporters](https://docs.micrometer.io/tracing/reference/reporters.html).

## 4. Choosing Based on Integration Requirements

| Practical Requirement | Well-Founded Choice |
| --- | --- |
| Infrastructure ingests traces via OTLP, wanting Boot 3.3 auto-configuration | OpenTelemetry bridge + OTLP exporter |
| System already uses Brave, with existing Zipkin and matching Brave extensions | Brave bridge + Zipkin reporter |
| Want to use OpenTelemetry while the current receiver is Zipkin | OpenTelemetry bridge + Zipkin exporter |
| Legacy services use Brave while central pipeline moves to a Collector | Consider sending Zipkin to the Collector's corresponding receiver, or plan a tracer migration |
| Only want to add trace export with no special constraints yet | Identify the ingestion protocol and operational model first, then choose one complete combination |

This table is a way to reason from compatibility requirements, not a conclusion that one tracer is always faster, lighter, or better than the other.

Questions to answer before editing dependencies:

1. Does the receiver accept OTLP, Zipkin, or another protocol?
2. For OTLP, does the receiver use HTTP/protobuf or gRPC?
3. Does the application already depend on proprietary Brave/OpenTelemetry APIs or extensions?
4. Which context propagation format do communicating services use?
5. Who manages SDK versions, export mechanisms, and runtime configuration?

If business code only uses Micrometer APIs, switching the implementation may have less impact than code calling Brave or OpenTelemetry types directly. However, you still need to verify tracing behavior, tags, sampling, and context propagation after the change.

### 4.1. A Collector Does Not Remove Per-Hop Compatibility Requirements

A forwarding path might look like this:

~~~text
Brave application
    |
    | Zipkin API
    v
Collector's Zipkin receiver
    |
    | export path configured by Collector
    v
Target backend
~~~

OpenTelemetry Collector provides a Zipkin receiver to accept spans in Zipkin format. [Collector Contrib: Zipkin Receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/zipkinreceiver).

In this diagram, the application still sends Zipkin. The fact that the Collector can forward onward later does not turn the application-side exporter into an OTLP exporter. Each hop needs the matching receiver, protocol, and configuration.

## 5. Two Independent Sample Configurations

The dependency snippets below apply to an **existing Spring Boot 3.3 application**. They assume Gradle already uses Spring Boot's dependency management and the required application starters are configured.

Do not merge both dependency blocks into the same runtime. Choose one option, then use the corresponding set of properties.

### 5.1. Option A: OpenTelemetry + OTLP over HTTP/protobuf

Gradle Groovy `dependencies` block:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

`application.properties` configuration for a test environment with a Collector running on the same host as the JVM:

~~~properties
spring.application.name=checkout-service
management.tracing.sampling.probability=1.0
management.otlp.tracing.endpoint=http://localhost:4318/v1/traces
~~~

Or equivalent YAML:

~~~yaml
spring:
  application:
    name: checkout-service

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Points that must align:

- Choose `micrometer-tracing-bridge-otel`.
- The receiver must expose the matching OTLP/HTTP path.
- For the traces ingestion path under OTLP/HTTP conventions, the URL includes `/v1/traces`.
- `localhost` is resolved from where the JVM runs. If the JVM is in a container, use an address reachable from that container.
- Endpoint, TLS, and authentication in a real environment must match the receiver's configuration.

**Do not omit the endpoint assuming Boot 3.3.0 always supplies a default address.** The experiment in section 8 confirms `OtlpProperties` in this version has a default endpoint of `null`.

`management.otlp.tracing` is the property group for OTLP trace export. [OtlpProperties Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpProperties.html).

### 5.2. Option B: Brave + Zipkin

`dependencies` section:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

Corresponding configuration:

~~~properties
spring.application.name=checkout-service
management.tracing.sampling.probability=1.0
management.zipkin.tracing.endpoint=http://localhost:9411/api/v2/spans
~~~

Or equivalent YAML:

~~~yaml
spring:
  application:
    name: checkout-service

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

This endpoint is Zipkin's span ingestion API. Do not use the trace search UI page URL as the data export endpoint.

If you want to use OpenTelemetry with the same Zipkin receiver, replace the **dependency pair** with:

~~~groovy
implementation 'io.micrometer:micrometer-tracing-bridge-otel'
implementation 'io.opentelemetry:opentelemetry-exporter-zipkin'
~~~

Keep Actuator and use the `management.zipkin.tracing.*` property group. Changing the bridge does not force the backend to change at the same time, but you must use an exporter compatible with the new bridge.

### 5.3. Sampling 1.0 Is for Verification

`management.tracing.sampling.probability=1.0` helps verify test traces by sampling all new root traces according to the local probabilistic policy.

It does not guarantee all data appears in the backend: sampling decisions inherited from parent context, blocked observations, export path errors, or Collector/backend filtering can still affect the outcome.

Do not treat setting 1.0 as proof that the bridge/exporter is working. You need to observe actual spans on the receiving side.

## 6. OTLP Is More Than Just a Port Number

### 6.1. HTTP/protobuf and gRPC Are Two Different Transports

| OTLP Transport | Common Port | How to Identify |
| --- | --- | --- |
| OTLP/HTTP | 4318 | HTTP endpoint, such as `/v1/traces` |
| OTLP/gRPC | 4317 | gRPC service, not an HTTP POST to the path above |

Port values are OTLP default conventions, not mandatory constraints for every deployment. A receiver can be configured on another port. [OTLP Specification](https://opentelemetry.io/docs/specs/otlp/).

In the integration under consideration, Spring Boot 3.3 auto-configures OTLP over **HTTP/protobuf**. If you want to use gRPC, you need to configure the appropriate gRPC exporter and understand how auto-configuration backs off in favor of custom configuration. [OtlpAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpAutoConfiguration.html).

Therefore, changing to:

~~~properties
management.otlp.tracing.endpoint=http://localhost:4317
~~~

does not automatically turn an HTTP exporter into a gRPC exporter. An open port and reachable host are still not enough if the protocol mismatches.

### 6.2. Match the Signal Type

Also distinguish:

~~~text
/v1/traces   → trace
/v1/metrics  → metric
/v1/logs     → log
~~~

`management.otlp.metrics.export.*` configures metric export, whereas `management.otlp.tracing.*` configures trace export in Spring Boot 3.3. Configuring OTLP metrics does not replace choosing a tracing bridge and trace exporter. [Spring Boot 3.3: Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

A Collector receiving metrics is not proof that tracing is configured properly.

## 7. Cross-Service Context Propagation Is a Separate Decision

The exporter answers the question: **Where are spans sent, and in what format?**

The context propagation mechanism answers the question: **How does the downstream service know which trace it is participating in?**

~~~text
Service A ── HTTP request and context headers ──> Service B
    |                                                 |
    +── export spans to Collector/backend             +── export spans
~~~

Two services can share the same backend yet produce two disconnected traces if context is not propagated/extracted properly.

- W3C Trace Context specifies headers such as `traceparent` and `tracestate`. [W3C Trace Context](https://www.w3.org/TR/trace-context/).
- B3 has single-header and multi-header formats; it is a context propagation format, not a protocol for exporting spans to Zipkin. [OpenZipkin: B3 Propagation](https://github.com/openzipkin/b3-propagation).

Therefore, do not assume "Brave only propagates B3," "OpenTelemetry only propagates W3C," or "exporting to the same Zipkin guarantees traces connect." You must check each service's propagation configuration.

### 7.1. Example of Intentional Propagation Configuration

In Spring Boot 3.3.0, you can configure consumed and produced formats separately:

~~~properties
management.tracing.propagation.consume=W3C,B3,B3_MULTI
management.tracing.propagation.produce=W3C
~~~

This example allows consuming the listed formats and producing W3C. Section 8 verifies these are also the default values on the configuration properties object in the 3.3.0 version used here.

`management.tracing.propagation.type` is the unified property for both consuming and producing; when set, it overrides the corresponding granular settings. Do not set multiple properties simultaneously while ignoring this precedence rule.

You also need to check how HTTP clients are constructed. In a Boot application, use auto-configured builders such as `RestTemplateBuilder`, `RestClient.Builder`, or `WebClient.Builder` to receive context propagation integration. [Spring Boot 3.3: Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.tracing.propagating-traces).

### 7.2. Switching Bridges Requires End-to-End Verification

When migrating a service from Brave to OpenTelemetry or vice versa:

1. Remove the old bridge from the runtime classpath.
2. Re-select the exporter/reporter for the new implementation.
3. Keep or update the endpoint to match the ingestion protocol.
4. Verify neighboring services can read the new context.
5. Compare trace IDs, parent-child relationships, service names, and key metadata.
6. Check extensions or code using proprietary APIs of the old tracer.

The verification goal is that a request can traverse the services with its execution path still traceable, not merely that the application starts without errors.

## 8. Java Experiment: Inspecting Spring Boot 3.3.0 Properties

This experiment verifies **configuration property binding** and default values. It does not initialize a bridge, exporter, or connect to a Collector/Zipkin.

The code was compiled with `javac --release 17` and run on JDK 21 using Spring Boot **3.3.0** configuration classes. Explicitly noting the version avoids carrying default values from another version into the explanation.

### 8.1. Dependency File for the Standalone Experiment

Create `pom.xml`:

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
    <artifactId>trace-configuration-probe</artifactId>
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
</project>
~~~

No bridge is added to the experiment POM because the goal here is reading the configuration properties objects. Real trace-exporting application examples in section 5 still require the corresponding bridge and exporter/reporter.

### 8.2. Complete Program

Save `TraceConfigurationProbe.java` next to `pom.xml`:

~~~java
import java.util.Map;

import org.springframework.boot.actuate.autoconfigure.tracing.TracingProperties;
import org.springframework.boot.actuate.autoconfigure.tracing.otlp.OtlpProperties;
import org.springframework.boot.actuate.autoconfigure.tracing.zipkin.ZipkinProperties;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

public class TraceConfigurationProbe {
    public static void main(String[] args) {
        OtlpProperties otlp = bind("management.otlp.tracing", OtlpProperties.class,
                Map.of("management.otlp.tracing.endpoint",
                        "http://collector:4318/v1/traces"));
        ZipkinProperties zipkin = bind("management.zipkin.tracing", ZipkinProperties.class,
                Map.of("management.zipkin.tracing.endpoint",
                        "http://zipkin:9411/api/v2/spans"));
        TracingProperties tracing = bind("management.tracing", TracingProperties.class,
                Map.of("management.tracing.sampling.probability", "1.0"));

        System.out.println("OTLP_DEFAULT_ENDPOINT=" + new OtlpProperties().getEndpoint());
        System.out.println("OTLP_CONFIGURED_ENDPOINT=" + otlp.getEndpoint());
        System.out.println("ZIPKIN_DEFAULT_ENDPOINT=" + new ZipkinProperties().getEndpoint());
        System.out.println("ZIPKIN_CONFIGURED_ENDPOINT=" + zipkin.getEndpoint());
        System.out.println("SAMPLING_PROBABILITY=" + tracing.getSampling().getProbability());
        System.out.println("PROPAGATION_PRODUCE=" + tracing.getPropagation().getProduce());
        System.out.println("PROPAGATION_CONSUME=" + tracing.getPropagation().getConsume());
    }

    private static <T> T bind(String prefix, Class<T> type, Map<String, String> values) {
        Binder binder = new Binder(new MapConfigurationPropertySource(values));
        return binder.bind(prefix, Bindable.of(type))
                .orElseThrow(() -> new IllegalStateException("Cannot bind " + prefix));
    }
}
~~~

The three `bind(...)` calls use three separate property sources for OTLP, Zipkin, and general tracing policy. These are test inputs for the property binder; this is not a configuration activating two span-sending paths at once.

### 8.3. Run Commands

PowerShell/Windows:

~~~powershell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out TraceConfigurationProbe.java
java -cp "out;lib/*" TraceConfigurationProbe
~~~

Linux/macOS:

~~~shell
mvn -q dependency:copy-dependencies -DoutputDirectory=lib
mkdir -p out
javac --release 17 -encoding UTF-8 -cp "lib/*" -d out TraceConfigurationProbe.java
java -cp "out:lib/*" TraceConfigurationProbe
~~~

The first run requires downloading dependencies if they are not already cached locally.

### 8.4. Verified Stdout

~~~text
OTLP_DEFAULT_ENDPOINT=null
OTLP_CONFIGURED_ENDPOINT=http://collector:4318/v1/traces
ZIPKIN_DEFAULT_ENDPOINT=http://localhost:9411/api/v2/spans
ZIPKIN_CONFIGURED_ENDPOINT=http://zipkin:9411/api/v2/spans
SAMPLING_PROBABILITY=1.0
PROPAGATION_PRODUCE=[W3C]
PROPAGATION_CONSUME=[W3C, B3, B3_MULTI]
~~~

Reading the output:

- `OTLP_DEFAULT_ENDPOINT=null`: do not rely on a built-in default endpoint in this version's configuration object.
- `OTLP_CONFIGURED_ENDPOINT` and `ZIPKIN_CONFIGURED_ENDPOINT`: the right keys bound to the right property groups.
- `ZIPKIN_DEFAULT_ENDPOINT`: includes the full `/api/v2/spans` API path.
- `SAMPLING_PROBABILITY=1.0`: sampling configuration was read.
- `PROPAGATION_PRODUCE` and `PROPAGATION_CONSUME`: illustrates that produced and consumed formats can have different value sets.

Nothing in stdout proves that a span has reached a backend. Verifying that requires testing the real application in the next section.

## 9. Verifying Trace Export Configuration in an Application

### 9.1. Inspect Actual Dependencies

With Gradle:

~~~shell
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-tracing-bridge --configuration runtimeClasspath
~~~

On Windows you can use `gradlew.bat`. In a multi-module project, run the task against the application's specific Gradle project, such as prefixing the project path before the task name.

With Maven:

~~~shell
mvn dependency:tree
~~~

What to look for:

- Exactly one of the two bridge artifacts.
- An exporter/reporter matching the right row of the compatibility table.
- No old bridge pulled in via transitive dependencies.
- Versions consistently managed by the Spring Boot BOM.

Do not treat removing a line in the build file as proof that the dependency disappeared from the runtime classpath.

Spring Boot provides a managed dependency list; declaring artifacts within that scope does not require pinning separate versions manually. [Spring Boot 3.3: Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html).

### 9.2. Inspect the Data Chain

Test with an identifiable request or test operation:

~~~text
Does the operation have an observation/span?
        |
        v
Is the corresponding tracer configured?
        |
        v
Is the span sampled and ended?
        |
        v
Does the exporter/reporter send to the right endpoint and protocol?
        |
        v
Does the Collector/backend receive it?
        |
        v
Can it be found by service, time range, and trace ID?
~~~

Check each hop:

1. An instrumented point actually ran; an uncompleted operation may not have been sent yet.
2. Sampling policy and parent context do not drop the test data.
3. The exporter/reporter matches the active tracer.
4. The receiver exposes the right receiver and API path.
5. DNS, address, port, TLS, and authentication fit the JVM's runtime environment.
6. Batching is accounted for; abrupt process termination can prevent buffered data from being sent.
7. UI time-range or service-name filters are not hiding newly received data.

When testing a bridge switch, use the same request scenario to compare before and after. Trace IDs are generated dynamically, so there is no fixed value to copy as reference stdout.

### 9.3. Distinguishing Levels of Evidence

| Observed Evidence | What Can Be Concluded | What Cannot Yet Be Concluded |
| --- | --- | --- |
| Dependency is on the runtime classpath | Library is available for configuration | Exporter is already working properly |
| Tracer bean exists | An implementation is wired into the application | Every operation has a span or spans have been sent |
| Log contains a trace ID | Tracing context existed at log time | Backend has stored the trace |
| Exporter sends successfully to Collector | The application → Collector hop has evidence of working | Every hop after the Collector succeeded |
| Span/trace is searchable in the backend | The test data's export path reached its destination | Every service and error scenario is correct |

Making this distinction avoids repeatedly swapping dependencies when the actual issue is the endpoint, receiver, or how data is queried.

## 10. Common Errors and How to Resolve Them

| Symptom/Configuration | Where to Check | Resolution |
| --- | --- | --- |
| Both bridges are present | Direct and transitive dependencies | Keep one bridge; exclude the path pulling in the other |
| Brave with OpenTelemetry OTLP exporter without expected export | Mismatched tracer and exporter | Choose OpenTelemetry + OTLP, or design a Zipkin hop via Collector |
| OpenTelemetry with Brave Zipkin reporter | Mismatched implementation | Use `opentelemetry-exporter-zipkin` for the OpenTelemetry branch |
| OTLP sent to gRPC port using HTTP configuration | Receiver protocol | Keep HTTP/protobuf with the right endpoint or configure a separate gRPC exporter |
| Zipkin endpoint is the UI URL | Span ingestion API path | Use the corresponding `/api/v2/spans` endpoint |
| Configured OTLP metrics but no traces | Signal type mix-up | Check `management.otlp.tracing.*` and tracing dependencies |
| Trace ID appears in logs but no trace is visible | Export, sampling, search filters | Check each hop rather than treating logs as confirmation of storage |
| Two services produce two disconnected traces | Headers and HTTP client | Check consume/produce and context propagation integration |
| Overrode one SDK version and hit linkage errors | Version conflict | Return to the BOM-managed compatible set, then inspect the dependency tree |
| Switched bridge but data is duplicated | Old instrumentation, agent, or old pipeline still active | Identify who owns instrumentation points and export paths before adding new config |

Do not assume OpenTelemetry Agent configuration variables automatically control all Boot-managed Micrometer integration. Identify which component initializes the tracer/SDK/exporter and which configuration source that component reads.

## 11. Selection and Verification Exercises

1. The receiver only exposes OTLP/HTTP at `4318/v1/traces`. Choose the bridge, exporter, and endpoint configuration key. Explain why picking Brave and adding the OTLP exporter does not satisfy the auto-configuration under consideration.
2. An application currently sends Brave to Zipkin and wants to switch to OpenTelemetry while keeping Zipkin. Identify the dependency pair to replace and the endpoint group that can remain.
3. A backend is named "OpenTelemetry Collector" yet its receiver only accepts Zipkin. Determine which protocol the application must send on the first hop; do not decide solely by product name.
4. A Collector only exposes OTLP/gRPC on 4317. Explain why changing the port in the OTLP/HTTP configuration is not enough.
5. Service A produces W3C while B only consumes B3. Explain why exporting to the same backend does not automatically connect the two traces.
6. Run the property-checking program, then state clearly what was verified and what still requires testing against a real backend.
7. Inspect the runtime classpath of an existing application and document one complete path: common API → bridge → tracer → exporter/reporter → protocol → receiver.

A complete selection must align implementation, export mechanism, and ingestion protocol. Remembering only the names OpenTelemetry or Brave is not enough to build a verifiable tracing pipeline.
