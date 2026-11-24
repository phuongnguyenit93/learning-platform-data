# Identifying Broken Traces, Duplicate Spans, and Overlapping Observation Configurations

A request travels from service A to B, yet the tracing UI displays two disconnected trees. After adding an observability library, a single HTTP call appears as multiple nearly identical spans. Both situations make telemetry hard to read, yet the root causes may lie at completely different layers.

To fix the issue accurately, separate three questions: is context propagated continuously, is one piece of work measured multiple times, and is one record sent or ingested multiple times? This lesson builds a diagnostic method for Spring Boot 3.3.x with Micrometer Observation/Tracing, while highlighting what to check when an OpenTelemetry Java agent or a collector sits in the middle.

## 1. Viewing the Observability System Along the Data Path

```text
Work to observe
  → instrumentation code creates observation or span
  → tracer manages current trace/span
  → propagator passes context across network or thread switch
  → exporter sends completed span
  → collector processes and forwards
  → storage system and query UI
```

Instrumentation determines **which work is measured**. The tracer determines **which trace that work belongs to**. The propagator carries linking metadata across processing boundaries. Exporters and collectors deliver data to storage.

A single observation can be processed by multiple handlers for different purposes, such as timing metrics and span creation. Thus, seeing multiple handlers does not mean configuration is duplicated. Check which kinds of data they produce from the same context. Refer to [Observation lifecycle and ObservationHandler in Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/observation/introduction.html).

| Symptom | What Was Observed | What Cannot Yet Be Concluded Immediately |
| --- | --- | --- |
| A and B use two trace IDs for the same verified call | Signs of lost context continuity | Not yet known whether lost at client creation, outbound header, inbound header, or thread switch |
| B shares trace ID with A yet parent span is missing | Visible data lacks parent link | Not yet proved context propagation was lost |
| Two similar spans have different IDs | Two spans were created | Not yet proved work was measured redundantly |
| One span ID appears in multiple records | Multiple records share the same identifier | Not yet proved business logic executed multiple times |
| Multiple observability libraries exist at runtime | Multiple components are potentially active | Not yet proved all of them are enabled |
| Two identical log lines appear | Duplication occurred in logging | Not yet proved two spans exist |

Log information is supporting evidence. MDC can be missing or overwritten; do not use a `traceId` string in logs alone as final proof of the tracer's actual context.

## 2. Defining a Valid Path Before Hunting for Bugs

Suppose it is verified that an inbound HTTP request to A triggers one HTTP call from A to B, with no retries and without crossing an intentionally detached workflow. Under the separate-span client/server model, the expected tree looks like:

```text
Trace T
└── A: SERVER, span S1
    └── A: CLIENT, span S2, parent S1
        └── B: SERVER, span S3, parent S2
```

All three spans share `traceId=T`. B's receiving span links to A's client outbound span, so S3's `parentId` is S2, not S1.

The CLIENT and SERVER spans represent two perspectives of one network call. Their durations may be nearly equal; that does not make them duplicate spans. Business steps inside B can legitimately add INTERNAL spans.

This is the assumption for this lesson's practice. Some Brave/B3 systems support client and server contributing to a shared span. Spring Boot has `management.tracing.brave.span-joining-supported`, defaulting to `false`; enabling it requires B3 and compatible receivers. When encountering such data, also inspect `kind`, endpoints, and the `shared` flag before concluding duplication. See [Boot 3.3 tracing properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html) and [Zipkin span model](https://github.com/openzipkin/zipkin-api/blob/master/zipkin2-api.yaml).

Nor should you force "one business ID must have one trace" onto every architecture. Deferred scheduled jobs, batch processing, or fan-in from multiple sources may use separate traces and span links by design. Only call a trace broken after confirming that specific boundary is supposed to continue the same context.

## 3. Identifying a Broken Trace

### 3.1. Strong Signal: Continuity Breaks at a Verified Boundary

Expected data:

```text
A sends: trace=T1, span=S2
B receives: trace=T1, span=S3, parent=S2
```

Suspicious data:

```text
A sends: trace=T1, span=S2
B receives: trace=T2, span=S8, parent=none
```

If this truly is the same call and there is no intent to start a new trace, find where B failed to receive or use context T1.

With W3C Trace Context, `traceparent` carries trace ID, parent ID, and related flags. The receiver uses parent ID to link the new span to the existing path; do not copy parent ID as the receiver span's own ID in the separate-span model. Malformed headers may be rejected. See [Trace Context processing specification](https://www.w3.org/TR/trace-context/).

Track evidence point by point:

1. **Right before A sends:** which current span is active? Does the client create an outbound span?
2. **On the outbound request:** what does the propagation header actually contain?
3. **After proxy/gateway, at B's entry:** is the header still intact?
4. **Inside B during handling:** which trace ID and parent ID does the tracer receive?
5. **At the collector/backend:** do A's and B's spans share that linking metadata?

If the header was already missing leaving A, fixing B's consume configuration will not address the root cause. If the header arrived intact at B yet B started a new trace, focus on extraction and active tracers inside B.

### 3.2. Common Causes and How to Distinguish Them

| Boundary | Possibility to Check | Valuable Evidence |
| --- | --- | --- |
| HTTP client creation | Client created outside Boot's observation-integrated builders | Inspect actual client construction and headers on that specific call |
| Network transit | Proxy or custom code strips/overwrites headers | Compare before and after each intermediary |
| Context extraction | B only accepts a different format than A emits | Compare effective `produce`/`consume` configuration |
| Dispatching to executor | Work runs without restoring source context on target thread | Compare tracer at dispatch point and task start point |
| Reactor chain | Relied on `ThreadLocal` at assembly time, losing context at execution | Inspect inside actually running operators and after thread switches |
| Custom span code | Span was started without placing it in proper scope | Inspect span lifecycle and surrounding scope |
| Multiple independent SDKs/tracers | One component writes to a different context than the one used for HTTP | Compare tracer/SDK instances, config paths, and exported data |

With Spring Boot, auto-configured `RestTemplateBuilder`, `RestClient.Builder`, and `WebClient.Builder` are the primary integration paths for HTTP trace propagation. Creating clients outside those builders can lose automatic integration. Refer to [Spring Boot 3.3 tracing section](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

For executors, use an appropriate propagation mechanism, such as `ContextPropagatingTaskDecorator` in Spring Framework 6.1, and verify work runs through the configured executor. For Reactor, check `spring.reactor.context-propagation` and context at execution time. Copying MDC only carries strings for logging; it does not replace tracer context propagation.

### 3.3. "Missing Parent Span" Is Not Always Context Loss

You may see `traceId=T1` and `parentId=S2` at B without finding S2. Other possibilities include:

- The parent span has not finished yet so it has not been exported, or data arrived late at the receiver.
- Sampling decisions or filters across layers did not retain all pieces being queried.
- Exporter queue filled up, network failed, or process exited before flushing.
- The query is constrained by time range, service, environment, or data partition.
- The parent span lives outside the collected system boundary, such as an external client.
- The record has data yet the UI is only displaying a subset.

In these cases, context linking may still be intact. Check the exporter, collector, and query before changing propagators.

For example, explicitly sending a `traceparent` from curl with an arbitrary parent ID gives the server span an external parent. If curl never exported that parent span, its absence in storage is expected.

## 4. Distinguishing Forms of "Duplicate Spans"

### 4.1. Two Spans with Different IDs Measuring the Same Boundary

A tree worth inspecting:

```text
A: SERVER
└── A: CLIENT created by framework HTTP integration
    └── A: CLIENT created by custom wrapper
        └── B: SERVER
```

If it is verified that only one HTTP send occurred, two CLIENT spans describing the same call, same target, and same work interval may indicate overlapping instrumentation.

Compare simultaneously:

- Service and instance creating the span.
- `kind`: CLIENT, SERVER, INTERNAL, PRODUCER, or CONSUMER.
- Operation, HTTP method, route, and target destination.
- Start/end timestamps and parent-child relationships.
- Instrumentation scope name and version if provided by the format.
- Actual execution count, retries, redirects, fallbacks, and business steps.

Matching names are only one clue. Two valid calls to the same API can share the same span name. Conversely, two overlapping instrumentations can assign two different names.

### 4.2. Same Identifier Appearing in Multiple Records

For data where the shared-span model is ruled out, if the same `traceId + spanId` pair, same source, and same content appear multiple times at a single destination, inspect the data transport path:

```text
One completed span
  ├── first exporter  ──→ same receiving system
  └── second exporter ──→ same receiving system
```

Or:

```text
SDK → Collector A → receiving system
  └→ Collector B → same receiving system
```

Also check retries on errors or ambiguous acknowledgments. Some receiving systems deduplicate records with identical IDs, so duplicate sends do not necessarily appear as two rows in the UI.

Compare **data at each hop**, not just row counts in the UI. Exporting the same span once to two different systems can be an intentional design; the problem above is multiple paths unexpectedly converging on the same target.

### 4.3. Cases Worth Keeping

| Seen | May Be Valid Behavior Because |
| --- | --- |
| One CLIENT span at A and one SERVER span at B | They measure two sides of the call |
| SERVER containing INTERNAL with a business name | It is a child step with distinct meaning |
| Multiple CLIENT spans on the same route | There may be multiple calls or real retries |
| Span at proxy/service mesh and span inside app | They may measure different network boundaries |
| One span with multiple events | Events are not new spans |
| Multiple handlers on one observation | Each handler may produce a different signal |
| One trace with multiple spans of the same name | Names are not unique identifiers |

The goal is eliminating duplicate measurement of the same responsibility, not forcing every request to have a fixed span count.

## 5. Finding Overlapping Observation Configurations

### 5.1. Mapping Who Is Measuring What

In the application being diagnosed, list the components actually active:

| Work or Layer | Likely Owner | Overlap Sign to Verify |
| --- | --- | --- |
| HTTP server | Spring MVC/WebFlux instrumentation or Java agent | Custom filter creates an extra SERVER span for the entire same request |
| HTTP client | Boot-integrated client or Java agent | Interceptor/wrapper creates an extra CLIENT span around the same send |
| Business method | Manual observation or annotation aspect | Both wrap the exact same operation for the exact same purpose |
| Tracing bridge | Micrometer bridge to Brave or OpenTelemetry | Multiple bridges/SDKs configured independently without a clear integration design |
| Observation lifecycle | Metric handler and tracing handler | Duplicate handlers registered for the same role or multiple span-creating paths on one context |
| Span export | Exporter or span processor | Multiple pipelines sending identical data to one place |
| Collection | Pipelines/Collectors | Same-source data looping or merging back into the same target |

Having `micrometer-tracing-bridge-otel` alongside OpenTelemetry libraries is a normal bridge relationship, not proof of two span-creating systems. Likewise, Actuator serves many features beyond tracing. Do not remove everything simply upon discovering the app has a Java agent.

### 5.2. Annotations and Manual Code Wrapping the Same Work

A typical scenario is a controller already observed by HTTP instrumentation yet having an observation added for that exact same HTTP boundary. When the `@Observed` aspect is active, the extra annotation can create another observation.

Another scenario is a method having both `@Observed` and an explicit `Observation.createNotStarted(...).observe(...)` wrapping its entire body.

How to resolve depends on measurement intent:

- If two layers measure the same responsibility, keep one appropriate layer.
- If you want to measure a distinct business step separately, place the observation on that step with a name and scope reflecting that work.
- If you only want to rename or enrich an existing observation, check the corresponding convention/customization mechanism before adding another measurement wrapper.
- Do not add annotations out of habit assuming more spans always mean better observability.

Spring Boot explicitly warns about duplicate observations when adding annotations onto already-instrumented components. See [annotations section in Observability documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html). Verify the aspect is actually active; an unprocessed annotation is not the cause of extra observations.

### 5.3. Java Agents, Starters, and Custom Configuration

An agent may be attached via `-javaagent`, container/IDE launch config, or JVM startup environment variables. It will not necessarily appear in the application's Gradle dependency tree.

If both an agent and in-app observation config are present:

1. Record the agent version and effective active configuration.
2. Identify which instrumentation produces the suspected spans.
3. Check the integration or nested-duplicate-span suppression mechanisms for that exact version.
4. In a test environment, disable exactly one suspected measurement source and rerun the same case.
5. Keep the change only when data proves redundancy was removed while preserving required links.

The OpenTelemetry Java agent has mechanisms to suppress redundant nested spans and allows disabling individual instrumentations. That does not mean every custom setup outside the agent is automatically reconciled cleanly. Refer to [agent instrumentation control documentation](https://opentelemetry.io/docs/zero-code/java/agent/disable/).

Never use an app-wide tracing kill switch as a diagnostic conclusion. If all spans vanish together, you only lost data without identifying the source of duplication.

### 5.4. Inspecting the Running Configuration

In a standalone Gradle project used for practice, inspect runtime dependencies with:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency micrometer-tracing --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opentelemetry --configuration runtimeClasspath
```

In PowerShell, use `.\gradlew.bat` instead of `./gradlew`. In multi-module projects, run tasks on the exact subproject owning the application under inspection.

The dependency tree shows where libraries come from; it does not prove which auto-configurations are active. Also compare Boot's startup condition report using `--debug`, registry/tracer/provider/exporter beans created by the app, agent config, and active profiles.

Properties in YAML can be overridden by higher-precedence configuration sources. Record the effective values for propagation format, sampling rate, export endpoint, and enable/disable toggles rather than looking only at one `application.yml` file.


## 6. Controlled Reproduction Workflow

### 6.1. Shrink the Path While Keeping the Boundary Under Test

Pick one known A → B path. On the first pass, use a single request, no retries, and no noisy background traffic. Record app version, profile, agent, export destination, and the intended meaning of expected spans.

In a practice environment using Boot-managed tracing, you can temporarily configure:

```yaml
management:
  tracing:
    sampling:
      probability: 1.0
    propagation:
      type: w3c
```

This helps test with one propagation format and reduces sampling variance within the Boot-managed SDK. It does not automatically control an agent's sampler or Collector sampling/filtering policies. Nor does it fix packet loss, full queues, or misconfigured exporter endpoints.

`management.tracing.propagation.type` applies to both consume and produce and overrides granular `consume`/`produce` properties. If the system needs to accept multiple formats during migration, preserve that compatibility requirement in the real fix; do not switch the whole system to one format merely because a simple test case passed.

### 6.2. Sending a Known Context

Suppose two practice applications expose `GET /checkout` on port 8080 and `GET /stock` on port 8081; checkout calls stock via a tracing-integrated HTTP client. These are preconditions of the test scenario, not endpoints created by the Java program in section 7.

Send exactly one request:

```bash
curl -H "traceparent: 00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-1111111111111111-01" http://localhost:8080/checkout
```

On Windows you can use `curl.exe`. The Trace ID in the header has 32 hex characters and parent ID has 16 characters; neither is all zeros. The trailing flag `01` indicates a sampled decision in the incoming context.

When the apps accept this context under the test configuration, verify:

- A's SERVER span belongs to trace `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, with external parent `1111111111111111`.
- The CLIENT span actually sending to B has its own ID and preserves that trace.
- The header sent from A to B carries that CLIENT span's ID as its parent ID.
- B's SERVER span preserves that trace and links to the outbound span, per the separate-span model under test.

Use a fresh trace ID for every trial. Sending multiple requests with the same fixed trace ID intentionally merges them into one trace, making span counts easy to misinterpret. Do not expect to see curl's parent span in the receiver if that span was never exported.

If the system has a policy to start a new trace at trust boundaries, verify against that policy; do not conclude the app is broken merely because it declined external context in the test.

### 6.3. Change One Hypothesis per Run

For example, if you suspect a custom interceptor creates an extra CLIENT span:

1. Save evidence from the run with the interceptor: IDs, kinds, parent-child relationships, HTTP send count.
2. Disable only the interceptor's span creation in the test environment; keep request-sending behavior unchanged.
3. Send a new request with a fresh context.
4. Confirm the extra span vanished, business execution count stayed unchanged, and B still linked properly into the trace.
5. Rerun both the success path and an error path.

If you simultaneously switch bridges, disable an agent, change samplers, and swap exporters, even if the UI looks cleaner you will not know which change fixed the bug.

### 6.4. Observing at the Collector

When you need to separate "application creates duplicates" from "forwarding pipeline duplicates," inspect data before and after each hop. With an OpenTelemetry Collector having the matching components, a local practice config to receive OTLP and print data might look like:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
```

This is a practice Collector that only prints data without forwarding to trace storage. Applications sending to it must use the matching protocol and endpoint; changing the destination address does not change the protocol format.

Compare trace ID, span ID, parent ID, service resource, kind, instrumentation scope, and timestamps. If data already has two spans with different IDs before entering the Collector, go back to span creation sources. If the source produced one record yet forwarding produced multiple copies with the same ID, focus on the pipeline/exporter.

Displayed field names and structure depend on version. Using the `debug` exporter and layer-by-layer inspection is documented in [Collector troubleshooting documentation](https://opentelemetry.io/docs/collector/troubleshooting/).

## 7. Runnable Experiment: One Unit of Work Wrapped by Two Observations

This experiment uses Micrometer Observation directly to isolate overlapping instrumentation. It runs no HTTP server, installs no agent, registers no span-creating handler, and sends no data externally. Consequently, output proves the number of observations created, not a complete trace.

Prepare `ObservationOverlapDemo.java` and a `lib/` folder containing compatible versions of `micrometer-observation` and `micrometer-commons`. One reproducible pair is both at version `1.13.0`, from the Micrometer line used with Boot 3.3. When integrating into a real project, follow the version set managed by your project.

The program creates three cases, each with its own registry:

- `single`: one observation wrapping one execution of the work.
- `overlap`: two observations with the same name wrapping the exact same single execution of the work.
- `business-child`: an outer observation and a separate observation for an inner business step.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

public class ObservationOverlapDemo {
    private static final class Probe
            implements ObservationHandler<Observation.Context> {
        private final List<String> started = new ArrayList<>();
        private int stopped;

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onStart(Observation.Context context) {
            started.add(context.getName());
        }

        @Override
        public void onStop(Observation.Context context) {
            stopped++;
        }
    }

    public static void main(String[] args) {
        run("single", null);
        run("overlap", "http.server.requests");
        run("business-child", "order.reserve");
    }

    private static void run(String label, String innerName) {
        ObservationRegistry registry = ObservationRegistry.create();
        Probe probe = new Probe();
        registry.observationConfig().observationHandler(probe);
        AtomicInteger work = new AtomicInteger();

        Observation.createNotStarted("http.server.requests", registry)
                .observe(() -> {
                    if (innerName == null) {
                        work.incrementAndGet();
                    } else {
                        Observation.createNotStarted(innerName, registry)
                                .observe(() -> {
                                    work.incrementAndGet();
                                });
                    }
                });

        System.out.printf("%s work=%d started=%s stopped=%d%n",
                label, work.get(), probe.started, probe.stopped);
    }
}
```

Compile and run in PowerShell/Windows, from the directory containing the file:

```powershell
javac --release 17 -encoding UTF-8 -cp "lib/*" ObservationOverlapDemo.java
java -cp ".;lib/*" ObservationOverlapDemo
```

On Linux/macOS, use the same compile command; the run command swaps the classpath separator:

```bash
java -cp ".:lib/*" ObservationOverlapDemo
```

Exact output:

```text
single work=1 started=[http.server.requests] stopped=1
overlap work=1 started=[http.server.requests, http.server.requests] stopped=2
business-child work=1 started=[http.server.requests, order.reserve] stopped=2
```

`work=1` across all three cases confirms the work executed only once. The different measurement counts come from how the work was wrapped, not from business logic running twice.

In the `overlap` case, two wrappers sharing `http.server.requests` simulate two sources claiming responsibility for measuring one boundary. In this example we know the meaning of both layers because we wrote them; in a real system you must still verify via data and configuration.

The `business-child` case also has two observations, yet `order.reserve` represents a distinct step. Merely seeing a count of two cannot distinguish the two designs. `stopped` shows the observations here ended properly; it also does not prove the measurement design is sound.

The name `http.server.requests` is hardcoded directly in the experiment. Setting that name does not turn an observation into real HTTP instrumentation. When an appropriate tracing handler exists in an application, observations can lead to spans; here the `Probe` handler simply records lifecycle events so we can observe the mechanics clearly.

## 8. Choosing the Fix Based on the Faulty Layer

### Context Lost Across a Call

Keep context creation and propagation consistent: use properly integrated clients, preserve required headers, align formats between sender and receiver, and propagate context across thread boundaries. For manual spans, manage start, scope, and end together.

Do not fix by copying the same string into `MDC.traceId` on both services. That can make logs look related while span data remains two separate trees.

### Two Sources Measuring the Same Responsibility

Keep one owner for that boundary. Remove redundant manual wrappers, drop unnecessary annotations, or adjust the right component's instrumentation. Keep business observations that carry distinct meaning.

If you need to change metadata on an existing observation, use the corresponding customization mechanism. Renaming a redundant span only makes it look less similar in the UI without eliminating the redundant measurement.

### Same Record Traveling Through Multiple Export Paths

Fix the exporter/processor/Collector topology so each record follows intentional paths. Check actual destinations, not just config names: two hostnames can resolve to the same ingestion system.

Do not change propagators to fix duplicate exported records. Context propagation and how many paths ship a completed span are two separate problems.

### Data Only Missing When Querying

Fix the query range, filters, sampling policy, or data delivery at the right layer. A span that already has the right `traceId` and `parentId` does not need to be recreated just to make the UI tree look complete.

Never leave 100% sampling enabled permanently as a cure-all for missing traces. Practice settings help eliminate one variable; production sampling must suit load and observability goals.

## 9. Verifying the Fix and Practicing Reasoning

An evidence-backed fix should satisfy these points:

1. **Continuity:** at boundaries expected to continue traces, the receiver uses the right trace ID and required parent link.
2. **Meaningfulness:** one execution does not have two layers measuring the same responsibility unintentionally; steps with distinct roles remain intact.
3. **Clean data path:** no unintended duplicate export paths feed the same destination.
4. **Proper scope:** after closing scope or reusing threads, new requests do not inherit context from earlier requests.
5. **Preserved behavior:** business execution counts, retries, and error handling remain accurate; reducing spans does not hide real errors.
6. **Explainability:** record the hypothesis, before-and-after evidence, exact change, and scope limits of the test run.

After a single-request run, test independent concurrent requests and an exception path. Verify each request keeps its own context, scopes close, and expected spans finish. If real retries occur, match attempt counts against spans per attempt rather than treating every extra span as a duplicate.

### Scenario A: B Switches Trace ID After a Thread Switch

A sends valid headers; B initially reads the same trace ID. After B dispatches work to a custom executor, the next downstream call starts a new trace. Where is the continuity break to check?

**Reasoning direction:** the data shows initial HTTP extraction was still working. Inspect context capture/restoration and the actual executor at the dispatch point, then inspect the tracer inside the target task. There is no basis yet to change network propagation formats.

### Scenario B: Two Similar Spans from Two Real Calls

Two CLIENT spans with the same name calling inventory appear shortly apart. Receiver logs confirm the first failed and the second succeeded; each span corresponds to one send.

**Reasoning direction:** this may be a valid retry. Inspect the retry policy and relationships between attempts. Removing a span merely because names match would lose failure and retry-cost visibility.

### Scenario C: One Span at Source, Two Records at Destination

SDK export logs one trace/span ID pair. Two pipelines both forward this record to one place; the receiver logs two ingestions.

**Reasoning direction:** prioritize inspecting forwarding paths and ingestion/deduplication behavior. There is no evidence here that business code or instrumentation created two distinct spans.

### Scenario D: Missing Parent After a curl Test

A has the trace ID from the test header and the tester-chosen parent ID, yet no parent span appears in the receiving system.

**Reasoning direction:** headers propagate relationships; they do not create or export parent span records. If curl never exported a parent span, its absence does not prove the trace broke. Separately test the A → B relationship where the test actually produces span data as proof.
