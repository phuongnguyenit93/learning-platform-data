# Tracer and Boot Version Compatibility

In the **SPRING_BOOT_OBSERVABILITY** module, Spring Boot uses **Micrometer Observation** as the integration point for metrics and tracing. **Micrometer Tracing** provides a facade so applications and frameworks can work with multiple tracer implementations. The underlying tracer can be OpenTelemetry or OpenZipkin Brave; meanwhile, the exporter determines which backend receives spans, such as an OTLP Collector or Zipkin.

Compatibility between a tracer and a Spring Boot version is not merely picking a dependency that compiles. The Boot version determines the managed dependency set, which auto-configurations are available, which property namespaces bind, and how the OpenTelemetry SDK is wired to Micrometer. Mixing bridges, SDKs, exporters, or starters from different generations can let an application start cleanly while creating no spans, exporting to the wrong endpoint, missing correlation, or running competing tracing pipelines.

This lesson helps you select a tracer aligned with your Spring Boot version, understand differences between Boot 3.x and 4.x, manage dependencies via the BOM, configure compatible exporters, and verify the entire path from Observation to the trace backend.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between Micrometer Observation, Micrometer Tracing, the tracer implementation, and the exporter.
2. Recognize the two common tracers supported by Spring Boot auto-configuration: OpenTelemetry and Brave.
3. Choose dependencies matching Spring Boot 3.x or 4.x.
4. Understand why two Micrometer tracing bridges must never sit on the classpath simultaneously.
5. Distinguish property namespace and starter changes across Boot versions.
6. Manage versions via Spring Boot dependency management / BOM.
7. Configure sampling, propagation, and exporters according to the tracer implementation.
8. Avoid creating multiple competing SDKs/providers or duplicate instrumentation.
9. Verify trace context across HTTP clients and servers.
10. Build a Boot/tracer upgrade workflow with testing and rollback.

## 2. Layers to Distinguish

| Component | Role | Examples |
| --- | --- | --- |
| Spring Boot Actuator | Auto-configuration and dependency management for observability/tracing. | Actuator starter and tracing auto-configuration. |
| Micrometer Observation | API describing an operation for multiple handlers to process. | HTTP server/client Observation. |
| Micrometer Tracing | Facade over a tracer implementation. | `Tracer`, `Span`, `Baggage` APIs. |
| Tracing bridge | Translates the Micrometer Tracing API to a concrete tracer. | `micrometer-tracing-bridge-otel` or `micrometer-tracing-bridge-brave`. |
| Tracer implementation | Creates spans/context and performs propagation. | OpenTelemetry SDK or Brave. |
| Reporter/exporter | Ships spans to a backend. | OTLP exporter or Zipkin reporter. |
| Collector/backend | Receives, processes, stores, and queries traces. | OpenTelemetry Collector, Zipkin. |

General flow:

~~~mermaid
flowchart LR
    App["Spring Boot application"]
    App --> Obs["Micrometer Observation"]
    Obs --> Trace["Micrometer Tracing handler"]
    Trace --> Bridge["One tracing bridge"]
    Bridge --> Impl["OpenTelemetry SDK or Brave"]
    Impl --> Export["OTLP exporter or Zipkin reporter"]
    Export --> Backend["Collector / trace backend"]
~~~

Observation is the application/framework abstraction. The bridge connects the abstraction to the tracer. The exporter/reporter ships the data. The backend does not dictate which bridge is used; the backend only needs to accept a compatible protocol.

## 3. Tracers Supported by Spring Boot

Spring Boot Actuator provides dependency management and auto-configuration for Micrometer Tracing. Common supported choices in Spring Boot include:

| Tracer | Common Backend / Export Format | Primary Bridge / Dependency |
| --- | --- | --- |
| OpenTelemetry | OTLP | OpenTelemetry tracing integration and OTLP exporter. |
| OpenZipkin Brave | Zipkin | Brave tracing integration and Zipkin reporter. |

Micrometer Tracing can also pair with other reporters/backends depending on version and dependencies. When relying on auto-configuration, however, follow the exact combinations documented for your running Spring Boot version.

### Choose Only One Bridge

Never include both dependencies at the same time:
- `micrometer-tracing-bridge-otel`
- `micrometer-tracing-bridge-brave`

An application should normally have only one primary tracer implementation. Having both bridges present can prevent auto-configuration from resolving the intended tracer, cause bean ambiguity, or create inconsistent pipelines. If you need to send data to multiple backends, consider exporter/collector fan-out from one tracer rather than adding two Micrometer bridges.

## 4. Compatibility by Spring Boot Version

Spring Boot lines have evolved how tracing integrations and property namespaces are packaged. The table below is directional; exact dependencies must come from your minor version's reference documentation and project dependency management.

| Spring Boot Version | OpenTelemetry Tracing | Brave Tracing | Export Config to Check |
| --- | --- | --- | --- |
| 3.0–3.1 | Micrometer OTel bridge and backend-specific exporter. | Micrometer Brave bridge and backend-specific reporter. | Backend-specific namespaces such as `management.otlp.tracing`, `management.zipkin.tracing`, or `management.wavefront`. |
| 3.2–3.5 | Micrometer OTel bridge + OTLP/Zipkin/Wavefront exporter per version. | Micrometer Brave bridge + Zipkin/Wavefront reporter per version. | Use matching `management.otlp.tracing` or `management.zipkin.tracing` / `management.wavefront`. |
| 4.x | Boot provides dedicated tracer-specific tracing integration modules/starters. | Boot provides dedicated Brave/Zipkin integration. | Tracing export properties organized under `management.tracing.export.*`; OTLP has a corresponding OpenTelemetry namespace in supported versions. |

This table is not a substitute for actual dependency metadata. Spring Boot 4.x changed artifact names and module structure; do not copy dependencies verbatim from a Boot 3.5 guide into Boot 4.x. Conversely, Boot 4.x property namespaces should not be backported onto Boot 3.x.

Official documentation to cross-check:
- [Spring Boot 3.5 Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Boot 4.0 Tracing](https://docs.spring.io/spring-boot/4.0/reference/actuator/tracing.html)
- [Spring Boot 4.1 Tracing](https://docs.spring.io/spring-boot/4.1/reference/actuator/tracing.html)
- [Spring Boot current Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)

## 5. Choosing OpenTelemetry with OTLP

OpenTelemetry fits well when your platform already uses an OpenTelemetry Collector or OTLP-capable backend. On Spring Boot 3.x, integration typically uses the Micrometer OTel bridge and OTLP exporter; on Boot 4.x, prefer the Boot-managed starter/module when specified by that version's reference guide.

### Spring Boot 3.x — Illustrative Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

This snippet illustrates the typical declaration in Boot 3.x. Do not specify explicit versions per dependency when Spring Boot dependency management already manages compatible versions. Check version references if using older 3.0/3.1 releases, as support matrices and exporter modules can differ.

### Spring Boot 4.x — Use the Boot-Managed Integration

Boot 4.x releases provide dedicated tracing integration modules/starters. Current documentation describes OpenTelemetry with OTLP via a starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Artifact names and module layout must match your exact minor version. Do not manually add duplicate bridge/exporter artifacts alongside the starter when the starter already pulls them in and auto-configures the pipeline. For advanced customization, use Spring Boot–provided exporter builder customizers rather than constructing a competing SDK.

### Configuring OTLP

In Boot 3.x, common properties in matching versions:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

In Boot 4.x versions with OpenTelemetry tracing export properties:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318
          transport: http
~~~

These two examples belong to different property generations. Verify endpoint semantics and transport per version; some versions take a full URL including the signal path, while others take a common/base endpoint and append the path automatically. Never copy properties from Boot 4 to Boot 3 or vice versa.

## 6. Choosing Brave with Zipkin

Brave is another tracer implementation supported by Micrometer Tracing. It fits well when an existing system uses the Zipkin ecosystem and wants to keep the corresponding reporter and protocol.

### Spring Boot 3.x — Illustrative Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

### Spring Boot 4.x — Boot-Managed Integration

In Boot 4.x releases, check the Brave and Zipkin starters/modules for your exact version rather than guessing artifact names from Boot 3.x. Current Spring Boot documentation still lists OpenZipkin Brave with Zipkin as a supported tracer combination.

### Configuring Zipkin

In Boot 3.x, common properties:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

In Boot 4.x versions, export properties are organized under that version's tracing export structure. Read the reference docs for that specific version before migrating configuration.

Never configure a Zipkin endpoint under an OTLP namespace. The Zipkin reporter sends the Zipkin protocol; the OTLP exporter sends OTLP. A backend supporting only one protocol cannot accept another protocol's payload merely by changing the URL.

## 7. Version Alignment with BOM and Dependency Management

Spring Boot dependency management is designed to align compatible versions across Spring Framework, Micrometer, Micrometer Tracing, and OpenTelemetry libraries. When using the Boot plugin/parent/BOM:

- Do not override individual Micrometer artifact versions unless justified and thoroughly tested.
- Never force a newer OpenTelemetry SDK version onto a starter managing a different version without checking binary compatibility.
- Avoid pulling in two bridges simultaneously via transitive dependencies.
- Inspect the dependency tree whenever duplicate SDKs, exporters, or reporters appear.
- When upgrading Boot, upgrade the plugin/parent/BOM together and re-test the tracing pipeline.

Gradle example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Versions in this example only illustrate one plugin pairing; use your project's approved Boot version and compatible plugins. With Spring Boot's Gradle dependency management setup, `io.spring.dependency-management` is not required in every configuration; declaration style depends on your project's build conventions.

Maven can use `spring-boot-starter-parent` or import the `spring-boot-dependencies` BOM to manage versions. Never mix the parent/BOM of one Boot version with plugins and starters of another Boot version.

## 8. Inspecting the Dependency Tree

When compatibility issues arise, inspect the dependency graph first:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Filter key artifacts:
- `micrometer-tracing`
- `micrometer-tracing-bridge-otel`
- `micrometer-tracing-bridge-brave`
- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp`
- `brave`
- `zipkin-reporter`

Maven:

~~~bash
mvn dependency:tree
~~~

Confirm:
1. Only one Micrometer tracing bridge is present.
2. The Micrometer Tracing version falls within the Boot-managed range.
3. OpenTelemetry API/SDK/exporter versions are not overridden to incompatible versions.
4. The reporter matches the chosen backend.
5. No Java agent or extra starter is unintentionally spinning up an extra pipeline.

If using the OpenTelemetry Java Agent, clarify whether the agent itself instruments and exports spans or whether the application also builds an SDK/exporter. Avoid duplicate spans caused by both the agent and application instrumentation measuring one operation without coordination.

## 9. Tracer-Dependent Sampling and Propagation

Micrometer Tracing provides a shared facade, yet samplers and propagators can have tracer-specific configuration.

Spring Boot defaults to sampling a small percentage of requests to avoid overloading backends; the common property is `management.tracing.sampling.probability`. With OpenTelemetry, supported versions may also allow selecting samplers such as `always-on`, `always-off`, `trace-id-ratio`, or `parent-based` variants via OpenTelemetry tracing sampler properties.

With Brave, sampling configuration and propagation must follow the Brave/Micrometer Tracing integration. Never assume OpenTelemetry-specific sampler properties apply to Brave.

### Propagation Formats

Common formats:
- W3C Trace Context: `traceparent` and `tracestate`.
- B3: single or multi-header formats.
- Baggage: W3C Baggage or matching baggage mechanisms.

Services must standardize on one format or configure appropriate composite propagation. If one service only reads B3 while another service only sends W3C, traces break even when both have active tracers.

### Parent-Based Sampling

With parent-based sampling, child services should honor the sampling decision propagated from the parent. This is crucial for keeping spans within the same distributed trace consistent. Avoid configuring independent samplers on individual services without understanding the impact on trace completeness.

## 10. Avoiding Multiple Tracing Pipelines

A common mistake is simultaneously combining:
- Spring Boot Micrometer Tracing auto-configuration.
- A manually constructed OpenTelemetry SDK in code.
- The OpenTelemetry Java Agent.
- A second Micrometer bridge.
- Another custom exporter or reporter.

When multiple components instrument and export together, you get duplicate spans, disconnected trace IDs, mismatched sampling decisions, or inconsistent resource attributes.

Before adding an SDK or exporter:
1. Identify which OpenTelemetry/`Tracer` bean Spring Boot manages.
2. Check whether an agent is already instrumenting HTTP/JDBC/Messaging.
3. Check whether client builders include auto-instrumentation and trace propagation.
4. Establish one primary pipeline per span source.
5. If multiple backends are needed, consider Collector fan-out rather than instrumenting twice in the app.

Spring Boot recommends using Micrometer Observation or the Micrometer Tracing API in application code rather than calling the OpenTelemetry API directly everywhere. This reduces direct coupling to a tracer implementation and makes switching tracers easier.

## 11. Compatibility Between Client Builders and Tracers

To propagate traces automatically over the network, use Spring Boot–auto-configured builders such as `RestClient.Builder` or `WebClient.Builder`. Instantiating `RestClient`/`WebClient` manually without those builders can skip automatic trace propagation.

Example:

~~~java
@Service
class InventoryClient {

    private final RestClient client;

    InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Whether you choose OpenTelemetry or Brave, the Boot-configured builder wires into the matching tracing integration. For custom HTTP clients, install the corresponding interceptor/instrumentation and verify context propagation.

Do not stop at verifying a span was created in the calling service; confirm `traceparent`/B3 headers are actually sent and the downstream server creates a child span with the same trace ID.

## 12. Resource and Service Identity

Resource attributes such as `service.name`, `service.version`, and `deployment.environment` should stay consistent across traces, logs, and metrics. If the service name varies across replicas or pipelines, the backend may display multiple service entities for the same application.

Example resource attributes configuration in supported versions:

~~~yaml
management:
  opentelemetry:
    resource-attributes:
      service.name: order-api
      service.version: "2.3.1"
      deployment.environment: production
~~~

Property namespaces and resource integration depend on the Boot version. If the application defines a custom `Resource` bean or standalone SDK, verify how it merges with the auto-configured Resource; avoid creating two differing Resource definitions for the same pipeline.

Never put request IDs, user IDs, or order IDs into `Resource`. Those values vary per request and belong in controlled span/log attributes, not service identity.

## 13. Upgrading Spring Boot Without Breaking Tracing

A Boot upgrade can change:
- Dependency versions and artifact names.
- Auto-configuration class and module boundaries.
- Property namespaces and defaults.
- The OpenTelemetry SDK version.
- Exporter builder customization APIs.
- Context propagation behavior.
- Default samplers and semantic conventions.

An upgrade workflow should include:

1. Record current versions of Boot, Java, Micrometer, Micrometer Tracing, tracer bridge, and exporter.
2. Read release notes and the tracing reference for the target Boot minor version.
3. Update dependencies to match the target version's starters/modules.
4. Remove duplicate bridges/exporters or unnecessary version overrides.
5. Migrate property namespaces if required by the target version's docs.
6. Verify sampling, propagation format, and resource attributes.
7. Run an integration test with at least one inbound request and one outbound call.
8. Verify in the trace backend that a complete trace appears with server and client spans.
9. Compare sampling rates, exporter failures, and trace volume before and after.
10. Roll out via canary and keep a rollback plan ready if trace completeness or ingestion shifts.

Never judge an upgrade solely by whether the application boots successfully. Tracing can silently lose instrumentation or exporting while business endpoints continue working normally.

## 14. Troubleshooting Tracer/Version Compatibility

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Boot does not create a `Tracer` bean | Missing Actuator/tracing bridge or wrong starter version. | Check runtime dependency tree and auto-configuration report. |
| Two `Tracer`/bridge beans exist | Both OTel and Brave bridges on classpath or duplicate custom config. | Keep only one bridge and clarify bean ownership. |
| Compile error after Boot upgrade | APIs/artifacts/packages changed across major versions. | Read migration guide and target version dependency metadata. |
| App starts yet exports no spans | Missing exporter/reporter, wrong endpoint, or pipeline disabled. | Inspect exporter bean, property namespace, and exporter logs. |
| Boot 3 config fails on Boot 4 | Property namespace or starter changed. | Consult reference docs for the exact target minor release. |
| Traces are duplicated | Agent and application auto-instrument the same operation. | Check agent extensions, starters, and custom interceptors. |
| Client span does not link to server span | Manually built client, incompatible propagation format, or stripped header. | Check Boot-injected builder and trace headers. |
| Sampling differs across services | Inconsistent custom samplers or parent-based behavior. | Compare sampled flags and sampler configuration. |
| Trace ID exists, wrong service resource | Custom `Resource` bean/SDK did not merge attributes as expected. | Inspect the Resource payload at the exporter. |
| Exporter class not found | Exporter artifact missing or version mismatch. | Inspect dependency tree and BOM. |
| `NoSuchMethodError` in OTel SDK | OTel modules overridden to incompatible versions. | Align OTel artifacts via dependency management. |
| Backend rejects protocol | Used OTLP exporter against a Zipkin endpoint or vice versa. | Cross-check protocol, receiver, and endpoint. |

## 15. Runbook to Verify Tracer Compatibility

1. **Identify Boot version:** verify which plugin/parent/BOM actually resolves.
2. **Identify Java version:** ensure the Java runtime matches the Boot major/minor version.
3. **Verify one bridge:** confirm the dependency tree contains only the OTel or Brave bridge as chosen.
4. **Verify exporter:** OTLP exporter pairs with an OTLP receiver; Zipkin reporter pairs with a Zipkin endpoint.
5. **Verify property namespace:** consult the exact version's reference docs; do not reuse YAML from a different major version tutorial.
6. **Verify beans:** confirm `Tracer`, `ObservationRegistry`, OpenTelemetry/Brave tracer, and exporter beans exist.
7. **Send a request:** produce one server span and one outbound client span.
8. **Verify propagation:** confirm W3C/B3 headers and continuous trace ID across services.
9. **Verify sampling:** compare probability, parent-based behavior, and sampled flags.
10. **Verify backend:** confirm the trace has complete spans, accurate `service.name` resource, and no duplicates.
11. **Verify agent:** confirm no Java agent double-instruments alongside application instrumentation.
12. **Record baseline:** exporter errors, spans/second, sampling ratio, and trace completeness.

## 16. Self-Check Exercises

### Exercise 1 — Choosing a Bridge

A Spring Boot application uses OpenTelemetry as its tracer. Which bridge dependency fits?

**Answer:** `micrometer-tracing-bridge-otel`. Do not add `micrometer-tracing-bridge-brave` at the same time.

### Exercise 2 — Zipkin Backend

An application uses Brave and wants to send traces to Zipkin. Should you configure the OTLP exporter simply because both are trace backends?

**Answer:** No. Use the Brave tracing integration and matching Zipkin reporter/properties. OTLP and Zipkin are two different protocols.

### Exercise 3 — Upgrading from Boot 3 to Boot 4

The build succeeds after a major version upgrade, yet traces stop exporting. What must be checked?

**Answer:** New artifacts/starters, auto-configuration, property namespaces, exporter beans, and dependency versions. Never assume Boot 3 configuration stays unchanged on Boot 4.

### Exercise 4 — Two Bridges on the Classpath

The dependency tree contains both the OTel bridge and the Brave bridge. Why must this be fixed?

**Answer:** An application should select one primary tracer implementation. Two bridges can cause auto-configuration ambiguity, competing beans, or inconsistent tracing pipelines.

### Exercise 5 — Broken Client/Server Trace

The client span and server span have different trace IDs. Should you raise sampling probability to 100%?

**Answer:** That does not fix the propagation root cause. Check Boot-auto-configured builders, trace headers, W3C/B3 compatibility, proxies, and async context.

### Exercise 6 — Multiple Backends

A team wants to send the same traces to two backends. Should they add a second bridge?

**Answer:** No. Keep one tracer and consider exporter/Collector fan-out or an intentional exporter pipeline configuration. Avoid instrumenting the same operation twice.

## 17. Deployment Checklist

- [ ] Identified Spring Boot major/minor version and Java runtime.
- [ ] Dependency versions managed via the appropriate Boot BOM/parent/plugin.
- [ ] Only one Micrometer Tracing bridge selected: OpenTelemetry or Brave.
- [ ] Exporter/reporter matches the protocol and backend.
- [ ] Starter/module names verified against the exact version's reference docs.
- [ ] Property namespaces not copied blindly between Boot 3.x and 4.x.
- [ ] No custom SDK/provider/tracer pipeline competing with auto-configuration.
- [ ] Sampling and parent-based behavior verified.
- [ ] W3C/B3 propagation aligned across services.
- [ ] `RestClient`/`WebClient` use Boot-auto-configured builders when automatic propagation is needed.
- [ ] Resource attributes `service.name`/`version`/`environment` kept consistent.
- [ ] Agents and application instrumentation do not produce duplicate spans.
- [ ] Integration tests verify server/client spans share the same trace ID.
- [ ] Backend receives the right protocol, endpoint, and service identity.
- [ ] Baselines captured for exporter errors, sampling ratio, and trace completeness before upgrading.
- [ ] Canary/rollback plan prepared for Boot/tracer changes.

**Remember:** The Spring Boot version governs dependencies, auto-configuration, and property namespaces; the Micrometer Tracing bridge governs the tracer implementation; and the exporter/reporter governs the shipping protocol. Pick one bridge, rely on Boot's dependency management, check the reference docs for your exact version, and test propagation from client to server. An application booting cleanly does not prove tracing compatibility; only complete traces exported to the right backend confirm the pipeline works.
