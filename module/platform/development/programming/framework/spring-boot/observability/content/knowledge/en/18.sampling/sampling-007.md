# Parent-Based Sampler

A request traverses API Gateway, Order Service, Inventory Service, and Payment Service. If each service picks sampling independently, the gateway might keep a trace while a middle service drops its spans, breaking the trace. The **Parent-based sampler** solves that consistency problem: when a span already has a parent, the sampler follows the parent's sampled/not-sampled decision; only when creating a new root span does the root sampler decide whether to sample.

The **Parent-based sampler** lesson belongs to the **Sampling** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module teaches setting up observability for Spring Boot with Micrometer Observation, metrics, logs, and distributed tracing; covering context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments.

> **Key idea:** A Parent-based sampler is not "flipping a weighted coin for every span." It is a composite sampler: **root spans use the root sampler**, while spans with a parent are decided by the branch matching the parent's sampled state (remote/local). With OpenTelemetry's default ParentBased configuration, a sampled parent leads to sampled children, and a not-sampled parent leads to not-sampled children. This keeps the entire trace consistent, while also propagating a root drop decision down to downstream spans.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the parent-based sampler and the distinct role of the root sampler.
2. Distinguish root spans, local parents, and remote parents.
3. Read the sampled flag in trace context and understand its effect on child spans.
4. Describe the four default branches of the OpenTelemetry ParentBased sampler.
5. Configure sampling in Spring Boot, understanding the role of probability and sampler type when using OpenTelemetry.
6. Contrast OTel behavior with other tracing bridges/tracers.
7. Evaluate the impact of root sampling on trace completeness and exporter cost.
8. Distinguish parent-based/head-based sampling from tail sampling in the Collector.
9. Test sampling decisions across multiple services and investigate missing traces.
10. Understand the risks of trusting sampled flags from remote callers.

## 2. Why Is a Parent-Based Sampler Needed?

A distributed trace typically comprises many spans across multiple services. If services apply ratio sampling independently, a trace can get fragmented. The Gateway may keep spans, Order drops spans, while Inventory keeps its own spans. The backend then shows gaps or spans missing their expected parent-child links.

The Parent-based sampler establishes a rule: **child spans inherit the sampling decision from their parent**. The root sampler selects the initial trace; from there, the decision is preserved across process boundaries when trace context propagates properly.

~~~mermaid
flowchart TD
    A["No parent context"] --> B["Root sampler"]
    B -->|Sampled| C["Root span is recorded/sampled"]
    B -->|Not sampled| D["Root span is not exported"]
    C --> E["Child span"]
    D --> F["Child span"]
    E --> G["ParentBased: follow sampled parent"]
    F --> H["ParentBased: follow not-sampled parent"]
    G --> I["Child sampled"]
    H --> J["Child not sampled"]
~~~

Parent-based sampling does not by itself guarantee the backend receives every span. Spans can still be missing because instrumentation did not create them, context propagation broke, a process crashed, the exporter/collector dropped data, or retention/queries missed them. It only keeps the sampling decision consistent when the sampler is invoked.

## 3. Root Span, Child Span, and Two Parent Types

A **root span** is a span with no valid parent context in the current trace. It typically appears at the inbound boundary of a new request, new message, or standalone job.

A **child span** is created within a context that has a parent. It shares the parent's Trace ID, has a new Span ID, and sets `parentSpanId` to the parent's Span ID.

~~~text
Trace T
  API Gateway server span       (root, sampled)
    Order Service server span   (child, sampled)
      Inventory client span     (child, sampled)
        Inventory server span   (child, sampled)
      Payment client span       (child, sampled)
        Payment server span     (child, sampled)
~~~

OpenTelemetry ParentBased distinguishes:

- **Local parent:** a parent span created in the same process/SDK context, e.g., a business span calling a DB span.
- **Remote parent:** context extracted from another process, typically via W3C `traceparent` or another propagation format.
- **No parent:** the sampler applies the root policy.

This distinction allows separate branches for remote parent sampled/not-sampled and local parent sampled/not-sampled. By default, OpenTelemetry's ParentBased handles sampled parents with `AlwaysOn` and not-sampled parents with `AlwaysOff`, for both local and remote parents.

## 4. The Four Default Branches of OpenTelemetry ParentBased

ParentBased is a decorator sampler with a mandatory root sampler and four optional parent branches. Default branches in the OpenTelemetry SDK:

| Parent exists? | Parent remote? | Parent sampled? | Default branch | Decision |
|---|---|---|---|---|
| No | N/A | N/A | root(root sampler) | Root sampler decides |
| Yes | Yes | Yes | remoteParentSampled = AlwaysOn | Sample child |
| Yes | Yes | No | remoteParentNotSampled = AlwaysOff | Do not sample child |
| Yes | No | Yes | localParentSampled = AlwaysOn | Sample child |
| Yes | No | No | localParentNotSampled = AlwaysOff | Do not sample child |

The **root sampler** can be `AlwaysOn`, `AlwaysOff`, or `TraceIdRatioBased`. ParentBased uses it only when there is no parent.

### 4.1 What Does a 10% Root Ratio Mean?

Suppose the root sampler uses `TraceIdRatioBased` with ratio `0.10`:

- Each root trace has roughly a 10% chance of selection using a deterministic algorithm based on Trace ID.
- If the root is sampled, child spans follow the sampled parent branch and are sampled.
- If the root is not sampled, child spans follow the not-sampled parent branch and are not sampled.
- Services do not independently roll a 10% ratio for each child of the same trace.

The 10% ratio is a probability for root traces, not a hard cap of "exactly 10 traces per 100 requests." Over short windows or low traffic, the observed rate can differ noticeably.

### 4.2 Parent Sampled Does Not Mean All Telemetry Is Stored

The ParentBased sampler decides whether a span is recorded/sampled by the SDK. It does not guarantee the exporter succeeds, the collector never drops, or the backend retains spans indefinitely. Distinguish:

1. Sampling decision in the SDK.
2. Span recorded in-process and finished properly through its lifecycle.
3. Processor/exporter sending the span.
4. Collector receiving and processing the span.
5. Backend storing and allowing queries.

A child having a sampled decision yet missing from the UI can still be caused by export, collector, or backend issues. Check each stage rather than immediately changing the root ratio.

## 5. How Sampling Decisions Propagate Over HTTP

W3C Trace Context carries Trace ID, parent span ID, and trace flags in the `traceparent` header. The sampled bit in trace flags is the part of context downstream uses to apply parent-based sampling.

Example where the root span is sampled and Order Service calls Inventory:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- Trace ID: `4bf92f3577b34da6a3ce929d0e0e4736`.
- Parent ID: `00f067aa0ba902b7`, identifying the sender's span.
- Trace flags `01`: sampled bit is set.
- Inventory extracts the remote parent context; ParentBased selects `remoteParentSampled` and samples the new server span.

If the sampled bit is off, under default ParentBased, `remoteParentNotSampled` will not sample the child.

### 5.1 Sampled Flag Is Not Backend Confirmation

The sampled bit can be propagated across processes, but it is not a receipt from the backend. It does not prove the exporter sent the span or the collector stored it. A trace with the sampled flag set can still be absent in the backend if the app crashed, export failed, the collector dropped it, or the query time window is wrong.

### 5.2 Remote Sampled Flag Is a Trust Boundary

If a public service trusts every remote sampled flag, callers can intentionally send requests with the sampled bit enabled to force downstream services to record more spans and inflate costs. Default ParentBased following parent decisions helps trace consistency, but internet-facing boundaries require explicit policies:

- Place a gateway/trusted ingress to manage or normalize tracing context.
- Choose appropriate sampler/branch policies if the SDK allows it.
- Cap exporter/collector resources, queues, and ingestion.
- Never use Trace ID or sampled flags to grant authorization.
- Monitor sampled rates, span volume, and dropped spans.

Do not manually alter the sampled bit inside individual services without a plan; doing so can fragment traces.

## 6. Configuring Parent-Based Sampler in Spring Boot

Spring Boot Actuator auto-configures Micrometer Tracing when compatible dependencies and a tracer bridge are present. Per current Spring Boot documentation, when using **OpenTelemetry**, the **management.opentelemetry.tracing.sampler** property supports these options:

| Sampler | Root decision / parent behavior |
|---|---|
| `always-on` | Sample every trace |
| `always-off` | Sample no traces |
| `trace-id-ratio` | Select ratio based on `management.tracing.sampling.probability`; not parent-based |
| `parent-based-always-on` | Sample child if parent sampled; root always sampled |
| `parent-based-always-off` | Sample child if parent sampled; root not sampled |
| `parent-based-trace-id-ratio` | Inherit parent decision; root uses configured probability |

With OpenTelemetry, current Spring Boot uses **parent-based-trace-id-ratio** by default. Spring Boot sets a default sampling probability of 10% to avoid overloading the trace backend. Exact properties/behaviors depend on Spring Boot version and tracer implementation. Refer to [Spring Boot Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).

### 6.1 Configuring a 10% Root Ratio

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

Interpretation:

- Root traces are selected at a 10% ratio.
- Child spans normally follow the parent's sampled/not-sampled decision.
- Downstream services must propagate and extract trace context properly to preserve the decision.
- Exporter/collector setup is separate; sampling YAML does not provide a backend on its own.

With Spring Boot using appropriate auto-defaults, setting probability may already select OpenTelemetry's default parent-based sampler. Declaring the sampler type explicitly avoids confusing a standalone ratio sampler with a parent-based ratio sampler.

### 6.2 Capturing 100% of Traces in Local Tests

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

With root ratio `1.0`, all root traces are selected; ParentBased carries that decision to child spans. Only use this in local/staging or carefully evaluated production windows because span volume can grow substantially. A working exporter/collector is still needed to observe results.

### 6.3 Sampling Zero Root Traces

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.0
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
~~~

The root sampler selects no root traces; default ParentBased also does not select children of not-sampled parents. This is not how you disable all instrumentation: Observations and metrics can still run, while trace spans are not sampled under this policy. If a sampled remote parent arrives, the remote-parent-sampled branch must be understood separately; root probability only decides traces without a parent.

### 6.4 Is Spring Boot Using Brave or OpenTelemetry?

Spring Boot supports different tracers, such as OpenTelemetry and OpenZipkin Brave. The property **management.opentelemetry.tracing.sampler** is for the OpenTelemetry sampler; it does not control the Brave sampler by default. **management.tracing.sampling.probability** is Spring Boot's sampling abstraction property, though parent-based details and bridge integration can differ. Check project dependencies, auto-configuration, and version documentation rather than assuming OTel sampler names apply to every bridge.

## 7. Parent-Based Sampling and Head-Based Sampling

ParentBased is typically used as a **head-based sampling strategy** where the root decision happens right when the trace begins. Deciding early saves recording/export overhead for unselected traces.

| Aspect | Independent per-span ratio sampler | Parent-based ratio |
|---|---|---|
| Root span | Decides by ratio | Uses root sampler |
| Child span | May re-roll independently | Follows parent decision by default |
| Cross-service consistency | Can break if services decide differently | Consistent when context propagates |
| Retaining complete traces | Not guaranteed | Increases likelihood of keeping spans of selected traces |
| Selecting error traces from final data | No | No, if root head decision already dropped the trace |

ParentBased is not a tail sampler. It does not wait for a trace to finish to check for errors, high latency, or special attributes before deciding to store the whole trace.

## 8. How Does Parent-Based Sampling Differ from Tail Sampling?

Tail sampling is usually performed at the Collector/backend after spans are sent to a central point. The Collector buffers data in memory/cache and decides according to a policy once spans arrive.

| Question | Parent-based/head-based | Tail sampling |
|---|---|---|
| When is the decision made? | When span is created, based on parent/root | After spans reach collector and match policy criteria |
| Visible information | Context and sampling attributes at creation | Can inspect received status, duration, and attributes |
| Advantage | Fast decision, reduces load upfront | Can keep error/slow traces based on final outcome |
| Disadvantage | Once root drops, full spans usually cannot be recovered | Requires memory/buffering, capacity, and trace routing |
| Best fit | Uniform volume reduction, preserving cross-service decisions | Keeping errors, high latency, special routes |

An architecture can combine root ParentBased in the SDK with tail sampling in the Collector, but if the SDK already dropped the root trace and never sent spans, the Collector lacks enough data to retain that trace. To let tail sampling keep error traces, enough spans must reach the tail sampler or a head/tail strategy matching cost constraints must be designed.

### 8.1 Why Can't the Collector Recover Unsent Spans?

The tail sampler can only decide based on data it receives. If the head sampler in the SDK dropped every span of a trace, the Collector cannot reconstruct lost duration, exceptions, or attributes. That is why head sampling decisions and tail policies must be designed as one cohesive pipeline.

## 9. Local Parent, Remote Parent, and Service Boundaries

A trace can include spans created inside the same process alongside spans extracted over the network. ParentBased distinguishes the two parent types, though OpenTelemetry defaults handle both by the same principle: sampled parent samples child; not-sampled parent does not sample child.

~~~mermaid
sequenceDiagram
    participant C as External client
    participant G as API Gateway
    participant O as Order Service
    participant I as Inventory Service
    C->>G: HTTP request (no parent)
    Note over G: Root sampler selects Trace T
    G->>O: HTTP + traceparent
    Note over O: Remote parent sampled/not-sampled
    O->>O: Local child span
    O->>I: HTTP + updated traceparent
    Note over I: Remote parent decision inherited
~~~

Example when the root sampler samples:

1. Gateway creates a sampled root span.
2. Gateway calls Order; Order extracts the sampled remote parent and samples the server child.
3. Order creates a local child for a business operation; `localParentSampled` selects sample.
4. Order calls Inventory; Inventory extracts the sampled remote parent and samples the server child.
5. The entire trace chain shares a consistent decision.

If Gateway does not sample the root, default ParentBased propagates the not-sampled decision to children. Trace context can still propagate so downstream knows the same Trace ID and does not start a new trace.

## 10. Losing Parent Context: Child Unintentionally Becomes a Root

If context is not injected/extracted, downstream can see the request as a new trace with no parent. The root sampler is invoked again, and sampling probability is re-applied. Consequences:

- Part of the downstream spans gets a different Trace ID from the original request.
- A downstream service creates a sampled root while the upstream trace was not sampled.
- The Trace UI shows multiple separate traces for one business journey.
- Observed trace rates diverge from expected sampling ratios.
- Log correlation shows inconsistent IDs.

Check instrumented HTTP client builders, inbound server instrumentation, W3C/B3 propagation formats, gateway header policies, and async context propagation. Do not switch ParentBased to a standalone ratio sampler to mask context bugs.

## 11. Parent-Based Sampler and Metrics/Logs

Tracing sampling does not mean sampling every telemetry signal:

| Signal | Typical effect of tracing sampler |
|---|---|
| Traces/spans | Decides whether spans are recorded/sampled per policy |
| Metrics | Does not automatically reduce Counters/Timers/Gauges by the same ratio |
| Logs | Does not automatically drop log events; governed by logging levels/filters/collector policies |
| Baggage/trace context | May continue propagating even when spans are not exported, depending on implementation |

For example, 10% root sampling does not mean only 10% of HTTP requests are counted in `http.server.requests`. Spring instrumentation can record metrics for every request while tracing exports only a subset of traces. Metrics provide aggregate statistics; traces provide detailed investigation of sampled requests.

Logs may contain `traceId`/`spanId` for requests that were not exported or cannot be found in the trace backend. Do not conclude log correlation is broken just because a trace was dropped by sampling.

## 12. Operational and Cost Impact

ParentBased helps reduce cost because when a root is not sampled, child spans are generally not sent either. When a root is sampled, the whole trace can generate many spans since each service, client call, database operation, or custom Observation can create spans.

Factors impacting volume:

- Request rate and root sampling ratio.
- Number of services/hops per trace.
- Spans created inside each service.
- Attributes, events, and links per span.
- Batch span processor queue/batch/flush cadence.
- Retries, timeouts, exporter failures, and collector backpressure.
- Collector/backend sampling and retention.

Lowering the sampling ratio is not the only way to reduce cost. You can remove redundant instrumentation, drop unnecessary attributes, limit events, eliminate duplicate spans, and tune the collector—while keeping enough traces for investigation and SLOs.

### 12.1 Root Ratio Is Not Span Ratio

If 10% of root requests are sampled and each trace averages 15 spans, total spans will approximate 10% of root traces multiplied by average span count, rather than 10% of independent spans. Traces vary unevenly in size, so a 10% root sampling ratio does not necessarily cut span volume by exactly 90% on every workload.

## 13. Testing the ParentBased Sampler

Testing should verify the decision matrix and full context chain, not merely confirm a property exists.

### 13.1 Decision Matrix

With default OTel ParentBased and a configured root ratio:

| Input context | Expected outcome |
|---|---|
| No parent; root ratio selects | Outcome per root sampler |
| No parent; root ratio rejects | Root not-sampled |
| Local parent sampled | Child sampled |
| Local parent not-sampled | Child not-sampled |
| Remote parent sampled | Child sampled |
| Remote parent not-sampled | Child not-sampled |

If a custom sampler overrides default branches, tests must match the actual policy. Do not assume every SDK wrapper uses the same default branches when custom configuration is present.

### 13.2 Multi-Service Testing

1. Pick a root request and configure easily observable sampling in the test (e.g., temporarily 100%).
2. Call Gateway → Order → Inventory.
3. Verify the same Trace ID, distinct Span IDs per span, and proper parent relationships.
4. Repeat with an unsampled root or not-sampled parent context.
5. Verify downstream does not independently sample children using the root ratio.
6. Create a case with context propagation disabled to observe downstream unintentionally starting a new root.
7. Cross-check SDK sampling decisions against exporter/collector: a trace missing from UI can be a pipeline issue, not necessarily the sampler.

Use a test exporter/in-memory span exporter if supported by your SDK version; do not depend on an external Zipkin/OTLP backend for every unit test.

### 13.3 Do Not Use Small Samples to Demand Exactly 10%

At a 10% root ratio, 50 requests can yield fewer or more than 5 sampled traces. Decisions are made by Trace ID rather than an exact counter guaranteeing 10 out of every 100. Unit tests for logic should use deterministic inputs or 0/1 ratio extremes; statistical integration tests need large sample sizes and tolerance bounds.

## 14. Common Pitfalls

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Gateway has trace, downstream missing spans | Remote parent not-sampled or export/propagation failure | Check sampled flag, sampler branch, exporter |
| Downstream creates a new Trace ID | Parent context not extracted | Check `traceparent`, client builder, proxy |
| Child span sampled despite not-sampled parent | Custom `AlwaysOn` branch or context lost creating new root | Check sampler config and parent context |
| One trace has fragmented spans | Inconsistent sampling, broken context, collector drops | Compare trace IDs, parent IDs, collector |
| Unexpectedly high trace volume | Root ratio raised, remote sampled flag trusted, span duplication | Check config, ingress, instrumentation |
| 10% probability yet seeing far fewer | Collector/exporter drops, low traffic, or another policy | Check SDK decision and exporter diagnostics |
| 10% probability yet seeing more traces than expected | Multiple independent root traces or broken propagation | Verify Trace IDs and root spans |
| Metrics complete while traces are only 10% | Normal behavior | Metrics/tracing sampling are independent |
| Log has `traceId` yet UI has no trace | Span not-sampled, not yet exported, retention/query | Check sampled flag and pipeline |
| OTel sampler property has no effect on Brave | Property targets OTel | Check matching tracer bridge/property |
| Remote parent sampled produces many spans | Following default parent decision | Guard ingress/trust boundary/collector |
| Tail sampler misses error traces | Head sampler dropped spans before collector | Redesign sampling pipeline |

## 15. Playbook: Investigating a Trace Broken Between Services

**Scenario:** Order Service has a trace, yet Payment Service has no span under the same Trace ID.

1. **Compare Trace IDs:** if they differ, determine where context broke or why Payment started a new root trace.
2. **Inspect outbound `traceparent`:** are parent ID and sampled flag valid?
3. **Check remote parent extraction:** does Payment receive the header and use the matching propagation format?
4. **Check Payment's sampler type:** if using OTel ParentBased, which branch do remote parent sampled/not-sampled hit?
5. **Check SDK/export:** child may be sampled, yet exporter/collector can still drop it.
6. **Check instrumentation:** are client/server spans actually created?
7. **Compare logs/metrics:** do HTTP or business operation metrics increment even without the trace?
8. **Verify after fix:** trace flows across the whole chain; root/child decisions are consistent.

Do not change production probability to 1.0 just to hunt for a missing trace before knowing whether the issue lies in root sampling, propagation, or export.

## 16. Self-Check Exercises

**Exercise 1 — Root and child.** The root sampler selects 10% of traces. A root is selected and creates three local children and two remote children. Under ParentBased defaults, which spans are sampled? Why don't children roll their own 10% ratio?

**Exercise 2 — Dropped root.** A root is not sampled and calls Order and Inventory. How do ParentBased defaults decide for children? Can trace context still propagate?

**Exercise 3 — Local vs. remote parent.** Explain the difference between the two branches. Under OTel defaults, how do their decisions differ when the parent is sampled/not-sampled?

**Exercise 4 — Spring Boot.** You use Spring Boot with OpenTelemetry, setting sampling probability `0.25` and sampler type `parent-based-trace-id-ratio`. Where does `0.25` apply? Does it re-apply to each child span?

**Exercise 5 — Tail sampling.** The Collector wants to keep every trace with an `ERROR`. If the SDK head sampler already dropped the root trace and sent no spans, can the Collector recover that trace? Why or why not?

**Exercise 6 — Metrics.** Tracing sampling is 10%, yet the HTTP request Counter still increments for every request. Is this a misconfiguration or normal behavior?

**Exercise 7 — Trust boundary.** An external caller sends a `traceparent` with the sampled bit set. Why can this increase cost? What policies can ingress/SDK/collector enforce?

**Exercise 8 — Practical probability.** A test sends 50 requests at a 10% ratio and sees 8 traces. Does this prove the sampler is broken? How should it be tested?

### Answer Hints

1. Because the root is sampled, all children follow the default sampled branches and are sampled as well.
2. Children follow the not-sampled parent and are not sampled; context can still propagate to preserve trace identity/decision.
3. Local parent is inside the same process, remote parent is extracted from another process; by default both use `AlwaysOn` when sampled and `AlwaysOff` when not-sampled.
4. `0.25` applies to root traces; children follow the parent decision rather than re-applying the ratio.
5. No; the collector cannot tail-sample spans that were never sent.
6. Normal; metrics and traces have independent sampling/export mechanisms.
7. Callers can trigger high span volume; enforce ingress policies, sampler branch/trust controls, resource caps, and monitoring.
8. No; small samples fluctuate. Test decision logic or deterministic 0/1 ratios; statistical integration tests need large sample sizes and tolerance.

## 17. Official References

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): sampling probability, supported OpenTelemetry sampler types, and default Spring Boot behavior.
- [Spring Boot 4.1 — Tracing](https://docs.spring.io/spring-boot/4.1/reference/actuator/tracing.html): OpenTelemetry parent-based sampler properties and sampler choices.
- [OpenTelemetry Specification — Trace SDK](https://opentelemetry.io/docs/specs/otel/trace/sdk/): ParentBased sampler, root/local/remote parent branches, and default behavior.
- [OpenTelemetry Java SDK](https://opentelemetry.io/docs/languages/java/sdk/): Java SDK samplers, ParentBased, and root sampler configuration.
- [OpenTelemetry Java Configuration](https://opentelemetry.io/docs/languages/java/configuration/): sampler configuration and ratio properties.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, trace flags, and sampled bit.
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/): tracer abstraction and tracing integration.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): sampling strategies and trade-offs.
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor): tail sampling policies at the collector.

**Remember:** A Parent-based sampler uses a **root sampler to decide new traces**, then preserves the parent's decision for child spans across local and remote boundaries. With OpenTelemetry/Spring Boot, `parent-based-trace-id-ratio` pairs with the root ratio configured via `management.tracing.sampling.probability`; children do not re-apply that ratio. This prevents selected traces from fragmenting, though dropped roots cannot be recovered by a Collector tail sampler if spans are never sent. Verify parent context, sampled flag, exporter, and collector stage by stage; keep metrics/logs as independent signals and protect trust boundaries when accepting external trace context.
