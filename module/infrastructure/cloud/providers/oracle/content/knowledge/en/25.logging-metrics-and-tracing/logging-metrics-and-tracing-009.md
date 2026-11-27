# Application Performance Monitoring and Distributed Tracing

In the **Logs, Metrics, and Tracing** chapter, Application Performance Monitoring (APM) helps you move from "the app feels slow" to a specific request: which services the request passed through, which step took time, and where errors originated. On Oracle Cloud Infrastructure (OCI), this telemetry is sent to an APM domain for search and analysis.

This lesson places tracing in an OCI operational context: resources reside in compartments, data readers hold appropriate IAM permissions, applications have network reachability to ingestion endpoints, and telemetry volume stays within budget. The lab uses two Java processes to generate a cross-service trace; production sections connect this to Compute, OKE, and applications accessing Oracle databases.

After this lesson, learners can:

- Distinguish trace, span, parent span, and context propagation.
- Choose an approach to instrument a Java application and ship traces to OCI APM.
- Read a trace to distinguish processing time, wait time, and downstream errors.
- Combine traces with logs and metrics; configure sampling and monitor the telemetry pipeline.

## 1. What Questions Does APM Answer?

Suppose an order API runs on OCI Compute or OKE:

~~~text
User → checkout-service → inventory-service → Oracle Database
                      └→ payment-service → payment gateway
~~~

An alert indicates p95 latency rose. Host CPU remains low; per-service logs show lines reading "request completed." What is missing is **the relationship among operations within the same request**.

| Signal | Question usually solved | Example in the order flow |
| --- | --- | --- |
| Metric | Since when and across what scope? | 5xx rate jumped over 5 minutes; p95 exceeded target |
| Log | What event happened at a point in time? | Connection timed out; validation rejected request |
| Trace | Where did the request go and how do steps relate? | Checkout waited on inventory; inventory waited on JDBC |
| Profile or deep JVM data | Where are CPU, memory, or threads spent? | A fee-calculation loop saturating CPU |

Traces provide evidence to isolate bottlenecks. A long JDBC span suggests the database call needs investigation; drawing conclusions about execution plans or locks inside Oracle Database still requires database-side telemetry.

OCI APM supports observing applications from multiple data sources, including Java agents, browser agents, tracers, and synthetic monitors. Browser agents capture real interactive sessions; synthetic monitors run scheduled proactive checks. These two views complement server-side traces. See [OCI APM Data Sources](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-data-sources.html).

## 2. Traces, Spans, and Causality

### 2.1. A Trace Consists of Multiple Spans

A **trace** represents the journey of a request or distributed job. A **span** represents a single operation with a start time, end time, and context.

Core fields:

| Component | Meaning |
| --- | --- |
| Trace ID | Shared identifier across all spans in one trace |
| Span ID | Identifier of an individual span |
| Parent span ID | Span that initiated the current operation; root span has no parent |
| Name | Operation name, kept stable like `POST /checkout` |
| Kind | Role such as `SERVER`, `CLIENT`, `INTERNAL`, `PRODUCER`, `CONSUMER` |
| Attributes | Key–value pairs describing the operation |
| Events, status | Timestamped events and operation outcome status |

Span names should describe the operation type; embedding order IDs into span names explodes the number of distinct names. Trace structure is described in [OpenTelemetry Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

Example span tree an application might emit:

~~~text
checkout: SERVER POST /checkout
├── checkout: INTERNAL validate-order
├── checkout: CLIENT GET inventory/stock
│   └── inventory: SERVER GET /stock
│       └── inventory: CLIENT SELECT stock...
└── checkout: CLIENT POST payment/authorize
    └── payment: SERVER POST /authorize
~~~

The client span and server span of a single remote call are two measurements taken from opposite sides. They share a trace, but each has its own Span ID. Applications only emit spans for instrumented code paths; deploying a database or load balancer does not automatically generate full spans for every hop.

### 2.2. Context Must Cross Service Boundaries

When A calls B, instrumentation on A injects context into the request; B extracts context and starts a child span. If headers are stripped or a library is uninstrumented, B starts a brand-new trace. Both services still have telemetry, yet the end-to-end journey is broken.

The same break occurs across executors, callbacks, or message brokers. Propagate context across execution boundaries and close scopes on time so requests do not bleed into one another. See [OpenTelemetry Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

W3C Trace Context defines the `traceparent` header. For version `00`:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- `00`: version.
- 32-hex-character group: Trace ID.
- 16-hex-character group: parent ID of the context-sending operation.
- `01`: sampled flag enabled.

`tracestate` carries vendor-specific tracing state. The sampled flag propagates the sampling decision; it does not guarantee every span was successfully stored by the backend. Inbound context from external callers is also not proof of user authentication. Format details live in [W3C Trace Context](https://www.w3.org/TR/trace-context/).

In systems running mixed agents, align on a propagator. If the browser emits B3 while the backend only reads W3C, configure compatibility at that boundary; never assume every agent shares the same default.

### 2.3. Asynchronous Work Requires Separate Interpretation

An HTTP request may return before a consumer finishes processing a queued message. In that case, user-facing latency and business completion time are two distinct quantities. Record message enqueue timestamps, queue wait times, and processing durations if you need to evaluate the entire workflow.

When an operation has multiple triggers, OpenTelemetry's model supports span links. However, OCI APM's OpenTelemetry endpoint documentation currently notes that **span links are not yet supported**. Verify backend capabilities before designing investigations around span links; this lab uses parent–child HTTP relationships. See [Configure OpenTelemetry for OCI APM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-opentelemetry.html).

## 3. OCI Components to Prepare

### 3.1. APM Domain, Compartment, and Region

An APM domain is the resource that aggregates application monitoring telemetry. It is distinct from an IAM identity domain used for identity management.

Example layout for this lab:

~~~text
Tenancy
└── Compartment ObservabilityLab
    ├── APM domain oci-java-tracing-lab
    └── Compute instance running two Java processes
~~~

Select the region before creating the domain and stay in that same region when opening Trace Explorer. In the Console, go to **Observability & Management → Application Performance Monitoring → Administration**, pick your compartment, and create an APM domain. Wait until the resource becomes active before retrieving endpoints.

Oracle offers Free Tier or paid domain options during creation. Read the actual tier choice, limits, and data retention published for the domain type you select; do not assume domain creation is free by default. See [Create an APM Domain](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-apm-domain.html).

### 3.2. IAM for Administrators and Analysts

Sample policies for identity domain `Default` and compartment `ObservabilityLab`:

~~~text
Allow group Default/ApmAdmins to manage apm-domains in compartment ObservabilityLab
Allow group Default/ApmReaders to read apm-domains in compartment ObservabilityLab
~~~

Replace the identity domain, group names, and compartment with your real values; place policies at a scope authorized to grant permissions on that compartment.

Admins create and manage domains; analysts read traces. For resource type `apm-domains`, the `use` verb also covers data key management operations, so do not grant `use` merely to let someone view traces. Full permission tables live in [OCI APM Policy Reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/apmpolicyreference.htm).

To read APM metrics in Metrics Explorer, users also need corresponding Monitoring permissions, for example:

~~~text
Allow group Default/ApmReaders to read metrics in compartment ObservabilityLab
~~~

Permissions to create alarms, use Notifications, and manage dashboards are additional requirements. See [APM Prerequisite Tasks](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/perform-oracle-cloud-infrastructure-prerequisite-tasks.html).

### 3.3. Endpoint and Data Keys

From the domain details page, retrieve:

- **Data Upload Endpoint**: destination URL receiving observations for the domain.
- **Private Data Key**: used for server-side telemetry upload paths in this lesson.
- **Public Data Key**: used by browser agents in their corresponding deployment model.

Each domain has its own endpoint and data keys. Data keys authorize ingestion; they do not replace IAM identities for opening the Console or querying data. Retrieval steps are in [Obtain Data Upload Endpoint and Data Keys](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/obtain-data-upload-endpoint-and-data-keys.html).

Store private keys in your runtime's secret management mechanism, restrict read access, and plan key rotation. Never embed private keys in client-side JavaScript, public container images, repositories, or startup logs.

### 3.4. Network Path from Application to APM

Separate the two traffic paths when designing networking:

~~~mermaid
flowchart LR
    U["Test request"] --> C["checkout-service"]
    C --> I["inventory-service"]
    C -. "HTTPS telemetry" .-> A["OCI APM domain"]
    I -. "HTTPS telemetry" .-> A
    R["Operator + IAM"] --> T["Trace Explorer"]
    A --> T
~~~

For the public upload endpoint used in the lab:

1. The Java host must resolve DNS and reach the endpoint over HTTPS.
2. Private subnets require an appropriate egress path, such as a NAT Gateway to the Internet or an organization-approved proxy.
3. Route tables, NSGs/security lists, and OS firewalls must permit the outbound traffic.
4. The JVM trust store must trust the certificate chain; check TLS inspection settings if using a proxy.
5. Never open inbound ports from the Internet to your app just so the agent can send telemetry.

Service Gateway is not a universal bypass route for every OCI hostname. Choose routing based on the exact endpoint and officially supported services. When moving the lab to OKE, also check Kubernetes network policies and pod egress paths.

## 4. Choosing an Instrumentation Approach

| Option | Suitable when | Operational responsibilities |
| --- | --- | --- |
| Oracle APM Java Agent | You want Oracle's built-in instrumentation and agent configuration | Installer, supported Java runtimes, agent version, and config |
| OpenTelemetry Java Agent | You want OpenTelemetry ecosystem instrumentation and OTLP export | Library compatibility, exporter, propagators, sampling |
| Manual API instrumentation | You need custom business spans auto-instrumentation cannot capture | Span lifecycle, context propagation, and attributes |
| OpenTelemetry Collector | You need centralized routing, filtering, or processing before backend upload | Collector resources, queues, secrets, high availability |

A Collector is a pipeline component; it does not automatically add spans to uninstrumented Java code.

This lab selects **OpenTelemetry Java Agent → OCI APM via OTLP/HTTP** without a Collector. The agent supports the Java HTTP Server and Java HTTP Client used below; for real applications, check exact library and version support in the [OpenTelemetry Java Instrumentation Supported Libraries](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/supported-libraries.md).

Attach only one tracing agent per JVM in the lab. When an app already bundles an observability SDK or starter, clarify which component initializes the SDK to avoid duplicate spans and double-exporting telemetry.

## 5. Lab: Sending a Distributed Trace from Two Java Processes to OCI APM

### 5.1. Objective and Prerequisites

Lab topology:

~~~text
curl → checkout-service :8080 → inventory-service :8081
          SERVER span          SERVER span
                 └ CLIENT span ──────┘
~~~

Both processes report to the same APM domain under different `service.name` values. When instrumentation and propagation work, a single call to checkout produces a trace spanning operations across both services.

Prerequisites:

- A Linux machine or OCI Compute instance with Bash, `curl`, and JDK 17 compatible with your chosen agent version.
- An active APM domain with its Data Upload Endpoint and Private Data Key retrieved.
- Trace read permissions, plus outbound HTTPS connectivity from the lab host.
- `opentelemetry-javaagent.jar` from an official release, placed in the lab directory.

Download the agent per [OpenTelemetry Java Agent Getting Started](https://opentelemetry.io/docs/zero-code/java/agent/getting-started/). Record the exact version used in the lab so future deployments remain reproducible.

The commands below run on the Linux lab host. Both services bind to loopback and simulate inventory in memory; the lab does not automatically create databases or OCI resources.

### 5.2. Application Code

Create `Demo.java` in your lab directory:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.Executors;

public class Demo {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    public static void main(String[] args) throws IOException {
        if (args.length != 1
                || !(args[0].equals("inventory") || args[0].equals("checkout"))) {
            throw new IllegalArgumentException(
                    "Usage: java Demo inventory|checkout");
        }

        boolean inventory = args[0].equals("inventory");
        int port = inventory ? 8081 : 8080;
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", port), 0);

        server.setExecutor(Executors.newFixedThreadPool(8));
        if (inventory) {
            server.createContext("/stock", Demo::stock);
        } else {
            server.createContext("/checkout", Demo::checkout);
        }

        server.start();
        System.out.println(args[0] + " listening on 127.0.0.1:" + port);
    }

    private static void stock(HttpExchange exchange) throws IOException {
        String traceparent = exchange.getRequestHeaders()
                .getFirst("traceparent");
        System.out.println("inventory received traceparent=" + traceparent);

        long delayMs = Long.parseLong(
                System.getenv().getOrDefault("STOCK_DELAY_MS", "50"));

        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            respond(exchange, 503, "inventory interrupted");
            return;
        }

        boolean fail = Boolean.parseBoolean(
                System.getenv().getOrDefault("STOCK_FAIL", "false"));
        respond(exchange, fail ? 503 : 200,
                fail ? "inventory unavailable" : "stock available");
    }

    private static void checkout(HttpExchange exchange) throws IOException {
        int responseStatus;
        String responseBody;

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:8081/stock"))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        try {
            HttpResponse<String> response = CLIENT.send(
                    request, HttpResponse.BodyHandlers.ofString());
            responseStatus = response.statusCode() >= 500 ? 502 : 200;
            responseBody = "inventory status=" + response.statusCode();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            responseStatus = 502;
            responseBody = "checkout interrupted";
        } catch (IOException exception) {
            responseStatus = 502;
            responseBody = "inventory request failed";
        }

        respond(exchange, responseStatus, responseBody);
    }

    private static void respond(
            HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders()
                .set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

Compile:

~~~bash
javac --add-modules jdk.httpserver Demo.java
~~~

The code does not inject `traceparent` manually or call any tracing API. The agent instruments the HTTP server and client automatically. Printing the header in `inventory` is a simple diagnostic check; it is not a full production mechanism for attaching Trace IDs and Span IDs to logs.

### 5.3. Configuring the Exporter

In **each terminal running a service**, run the following configuration block. Replace `APM_UPLOAD_BASE` with your real Data Upload Endpoint, including `https://` and no trailing `/`:

~~~bash
export APM_UPLOAD_BASE='https://<data-upload-endpoint-host>'

read -r -s -p 'Private Data Key: ' apm_private_data_key
printf '\n'
export OTEL_EXPORTER_OTLP_TRACES_HEADERS="authorization=dataKey $apm_private_data_key"
unset apm_private_data_key

export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="$APM_UPLOAD_BASE/20200101/opentelemetry/private/v1/traces"

export OTEL_METRICS_EXPORTER=none
export OTEL_LOGS_EXPORTER=none
export OTEL_PROPAGATORS=tracecontext
export OTEL_TRACES_SAMPLER=parentbased_always_on
export OTEL_RESOURCE_ATTRIBUTES='deployment.environment.name=lab,service.version=1.0.0'
~~~

OCI APM accepts traces at the private OTLP path with the `Authorization: dataKey ...` header. This configures traces only; the other two exporters are disabled to keep the lab focused on tracing. See [Oracle's OpenTelemetry Java Agent Example](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-opentelemetry.html).

Common points of confusion:

- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is the traces-specific URL; provide the complete path as shown.
- `OTEL_EXPORTER_OTLP_ENDPOINT` is the general endpoint setting; for OTLP/HTTP, the exporter appends signal-specific suffixes automatically. Do not swap between the two variables while keeping the same suffix assumption. See [OTLP Exporter Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/).
- The agent accepts system properties, environment variables, or config files; system properties take precedence over environment variables. When running in containers or service managers, verify the actual arguments received by the JVM. See [Java Agent Configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/).

Prompting silently for the key avoids typing secrets directly into shell history. Note that the value still remains in the process environment afterward; production deployments require proper secret management and process isolation.

`parentbased_always_on` is convenient for low lab traffic: root requests are sampled, and child spans inherit their parent's decision. Do not apply this rate blindly across all of production.

### 5.4. Running Inventory and Checkout

Terminal 1, after running the exporter config block:

~~~bash
OTEL_SERVICE_NAME=inventory-service \
STOCK_DELAY_MS=50 \
STOCK_FAIL=false \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo inventory
~~~

Terminal 2, also with the exporter config block loaded:

~~~bash
OTEL_SERVICE_NAME=checkout-service \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo checkout
~~~

Terminal 3 sends traffic:

~~~bash
for i in {1..10}; do
  curl -sS -o /dev/null \
    -w 'http=%{http_code} total=%{time_total}s\n' \
    http://127.0.0.1:8080/checkout
  sleep 0.2
done
~~~

Expected output:

- HTTP status from checkout is `200` when inventory operates normally.
- The inventory terminal prints a valid `traceparent` header.
- Once the exporter flushes batches and the backend processes them, Trace Explorer shows data for both services.

Do not expect latency to be exactly 50 ms: JVM startup, warm-up, instrumentation, and OS scheduling also contribute. If the apps run yet traces don't appear, check exporter logs and the pipeline before modifying business code.

### 5.5. Simulating a Slow Request

Stop only `inventory` with `Ctrl+C`. Keep the exporter environment variables in that terminal and restart it:

~~~bash
OTEL_SERVICE_NAME=inventory-service \
STOCK_DELAY_MS=800 \
STOCK_FAIL=false \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo inventory
~~~

Re-run the `curl` loop. The added delay should show up in the inventory server span and in checkout's wait for the inventory call. Because this delay is simulated with `sleep`, it demonstrates wait time—not CPU saturation in inventory.

### 5.6. Simulating a Downstream Error

Stop `inventory` and restart it with:

~~~bash
OTEL_SERVICE_NAME=inventory-service \
STOCK_DELAY_MS=50 \
STOCK_FAIL=true \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo inventory
~~~

Subsequent calls return `503` at inventory and `502` at checkout. Observe the HTTP status and error status on the corresponding spans. Error span count can exceed failed request count because one failure propagates across multiple layers.

After testing, restore `STOCK_FAIL=false` and `STOCK_DELAY_MS=50` to generate clean traffic again. A single successful trace after a fix proves recovery for that request; evaluating overall traffic still requires metrics over a time window.

### 5.7. Finding Traces in OCI

Open **Application Performance Monitoring → Trace Explorer**, select the right region, compartment, APM domain, and the time range when you ran the lab. Trace Explorer lets you search, filter, and inspect traces/spans; see [Monitor Traces in Trace Explorer](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/monitor-traces-trace-explorer.html).

Find the longest checkout traces:

~~~sql
show (traces)
  TraceId,
  ServiceName,
  OperationName,
  TraceDuration,
  ErrorCount
where ServiceName = 'checkout-service'
order by TraceDuration desc
first 20 rows
~~~

Take a Trace ID from the results and inspect all spans of that trace:

~~~sql
show (spans)
  TraceId,
  SpanId,
  ServiceName,
  OperationName,
  SpanDuration
where TraceId = '<trace-id-from-results>'
order by SpanDuration desc
first 50 rows
~~~

This is Trace Explorer's query language; do not run these two queries against Oracle Database. Filter values must match ingested telemetry. Use query assist or inspect span attributes when checking which dimensions were ingested. Syntax and clauses are documented in [Work with Queries in Trace Explorer](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/work-queries-trace-explorer.html).

Open a trace's details to verify:

1. Spans from both checkout and inventory share the same Trace ID.
2. Checkout's client span is the parent of inventory's server span.
3. The slow scenario shows increased duration on the inventory branch.
4. The error scenario shows corresponding statuses on both sides.
5. No duplicate twin sets of spans appear from attaching two agents.

Operation names, auxiliary span counts, and attribute rendering may vary across instrumentation versions. The primary criteria are the parent–child relationship and the behaviors you intentionally induced.

## 6. Reading a Waterfall to Isolate Issues

### 6.1. Nested Durations Do Not Add Directly

Suppose you observe these illustrative figures:

| Span | Relative start | Duration |
| --- | ---: | ---: |
| Checkout server | 0 ms | 910 ms |
| Checkout calling inventory | 40 ms | 850 ms |
| Inventory server | 55 ms | 810 ms |

Never add `910 + 850 + 810` to compute request latency. The lower two spans execute within the active window of the parent span above them. Checkout spent most of its time waiting on inventory.

Gaps between client and server spans can include connection setup, payload transfer, proxies, queuing in some places, and processing overhead outside the server span boundary. Do not blame the entire difference on the network without evidence.

### 6.2. Following the Critical Path

If checkout calls inventory and payment in parallel, request latency depends on whichever branch finishes last among those required for the response, plus any sequential steps. Summing durations of two parallel branches exaggerates user wait time.

When investigating:

1. Pick a slow trace with the same operation and conditions as a healthy baseline trace.
2. Compare branch structure, start offsets, and wait gaps.
3. Check for retries: multiple sequential calls to the same dependency.
4. Check uninstrumented gaps; those often represent uninstrumented local work.
5. Check host clock synchronization if timelines appear skewed abnormally.

A long span only reveals *which* operation took time. To distinguish CPU, locks, connection pools, or I/O, pull JVM metrics, pool metrics, and dependency telemetry.

### 6.3. When Accessing Oracle Database

Once JDBC is added to inventory, Java instrumentation can generate client spans around supported queries. Use them to spot slow calls, call frequency, and N+1 patterns, then cross-check with Oracle Database telemetry.

Separate three questions:

- Did the app wait to acquire a connection before the JDBC span even started?
- Which driver/library steps are included inside that span's duration?
- Does the database side show anomalous CPU, I/O, locks, or execution plans?

A JDBC span does not replace visibility inside the database. At the same time, review SQL capture settings so literals, bind values, or sensitive business data do not leak into telemetry.

## 7. Adding Business Spans or Using the Oracle APM Java Agent

### 7.1. Purposeful Business Spans

Auto-instrumentation typically covers HTTP, JDBC, and supported libraries. For domain steps like reserving stock or calculating limits, you may need custom business spans.

The extension below applies to applications carrying a compatible `io.opentelemetry:opentelemetry-api` dependency alongside the OpenTelemetry Java Agent. It is not required to compile `Demo.java` in the lab:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class BusinessTracing {
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("inventory-business");

    public static void reserve(Runnable action) {
        Span span = TRACER.spanBuilder("inventory.reserve").startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("inventory.operation", "reserve");
            action.run();
        } catch (RuntimeException exception) {
            span.addEvent("reservation.failed");
            span.setStatus(StatusCode.ERROR, "reservation failed");
            throw exception;
        } finally {
            span.end();
        }
    }
}
~~~

`makeCurrent()` binds the span to the active context for the scope lifetime; `end()` closes the measurement whether the action succeeds or throws. When invoked inside an instrumented HTTP handler, the new span inherits the active parent. Calling the API alone does not configure an exporter. See [OpenTelemetry Java API](https://opentelemetry.io/docs/languages/java/api/).

This example records only a neutral error event. If calling `recordException`, control exception contents because messages and stack traces can carry sensitive data. When work hops to another thread, propagate context explicitly to the worker thread instead of leaving a scope open arbitrarily on the old thread.

Favor spans on diagnostic business boundaries. Creating spans for every getter or every item in a large loop adds overhead and ingestion volume while cluttering investigations.

### 7.2. Deployment Path with the Oracle APM Java Agent

For systems using Oracle's own agent, download the installer from your APM domain and verify supported runtimes. Illustrative provisioning command:

~~~bash
java -jar ./apm-java-agent-installer-<version>.jar provision-agent \
  -service-name=checkout-service \
  -destination=/opt/checkout \
  -private-data-key=<private-data-key> \
  -data-upload-endpoint=<data-upload-endpoint>
~~~

This is a template; replace placeholders and inject keys via secure deployment pipelines before running. The four flags specify the service name, install path, data key, and endpoint. See [Provision the APM Java Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/provision-apm-java-agent.html).

After provisioning, add the agent to the JVM startup command:

~~~bash
java \
  -javaagent:/opt/checkout/oracle-apm-agent/bootstrap/ApmAgent.jar \
  -jar checkout.jar
~~~

Here `checkout.jar` represents a packaged application, not the `Demo.java` lab artifact. For WebLogic, Tomcat, Spring Boot, or containers, update the corresponding startup config and restart according to your environment. See [Deploy the APM Java Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/deploy-apm-java-agent.html).

The `OTEL_*` variables from the lab are not drop-in parameters for the Oracle APM Java Agent. Oracle's agent has its own sampling, abridging, and circuit-breaker mechanisms; consult [Oracle Agent Collection Options](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/introduction-apm-java-agent.html) when operating that path.

## 8. Correlating Traces with Logs, Metrics, and Alerts

### 8.1. Logs Should Carry Live Context

A log format might include:

~~~json
{
  "timestamp": "2026-11-21T03:20:00Z",
  "level": "WARN",
  "service": "inventory-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "7a3f82c9d10e456b",
  "message": "inventory dependency unavailable"
}
~~~

This is illustrative data. The application must read the active span's context or use log correlation supported by its agent and logging framework. `span_id` should identify the span actively executing when the log was emitted—not copy the inbound parent ID straight from the request header.

A realistic investigation workflow looks like:

~~~text
Error or latency alarm
  → identify service, operation, and time window
  → find a representative trace
  → grab Trace ID
  → search matching logs in OCI Logging or configured log store
  → cross-check dependency metrics
~~~

Attaching a Java tracing agent does not automatically configure application log shipping into OCI Logging. You still need a log pipeline and matching field extraction. A log can also contain a Trace ID even when the trace was dropped by sampling or ingestion errors; not finding a trace does not make the log invalid.

### 8.2. Using Metrics to Measure Scope of Impact

A single trace is one detailed observation. To gauge overall impact, monitor:

- Request rate by service and operation.
- Error rate at the user-facing boundary.
- Latency distribution, including p50, p95, or p99 where input data supports it.
- Saturation signals such as connection pools, thread pools, queues, CPU, and memory.

For example, an internal API target might be "at least 99% of valid requests complete under 1 second." When defining an SLI, specify which requests count, the time window, and the data source. Never divide error spans by total spans as a substitute for request error rate.

If you preferentially retain slow and error traces, stored traces do not represent all traffic. Error rates and percentiles derived from that sample will be skewed. Rely on dedicated SLI metrics collected across a well-defined request population, and use traces to explain specific requests.

### 8.3. Observing the Ingestion Pipeline Too

APM exposes ingestion health metrics in the `oci_apm` namespace, including `SpanIngestions` and `PayloadRejections`. Rejections can stem from invalid data keys, oversized payloads, or throttling. See [APM Metrics](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-metrics.html).

Design pipeline alerts around expected behavior:

| Symptom | What to verify |
| --- | --- |
| App traffic steady, span count drops sharply | Agent, sampling, exporter, and network path |
| Span count surges after a release | Duplicate instrumentation, retries, loops, or new operations |
| Payloads rejected | Keys, format, size, and ingestion limits |
| Missing data from one service | That JVM/pod's specific config and service name |
| Collector queue grows continuously | Export throughput, backend errors, resources, and queue limits |

A service with zero users overnight may emit zero spans legitimately. "No data" thresholds must account for traffic patterns or use deliberate synthetic traffic rather than treating every quiet period as an outage.

## 9. Sampling and Cost Control

### 9.1. Head Sampling vs. Tail Sampling

| Sampling mode | Decision timing | Trade-offs |
| --- | --- | --- |
| Head sampling | Near trace start | Cuts volume early; does not yet know if the request will fail later |
| Tail sampling | After collecting most or all spans | Can prioritize errors/slow traces; requires buffering and extra processing |

Sampling decisions should remain consistent per trace. Tail sampling cannot resurrect spans already dropped upstream by head sampling. See [OpenTelemetry Sampling](https://opentelemetry.io/docs/concepts/sampling/).

Example head-sampling configuration for OpenTelemetry Java, applied only after assessing traffic:

~~~bash
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
~~~

This samples roughly 10% of root traces by Trace ID while child spans follow their parent's decision. It is not a "keep all errors" rule. Java sampler options are documented in [Configure the SDK](https://opentelemetry.io/docs/languages/java/configuration/).

If you need tail sampling, you can introduce an OpenTelemetry Collector with an appropriate processor. Spans sharing the same Trace ID must route to the same decision-making Collector instance; account for memory, wait windows, and late-arriving spans. That is a Collector pipeline design requirement, not a built-in toggle of the lab domain. See [Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md).

### 9.2. Estimating Volume Before Picking a Sampling Rate

A rough volume estimate by span count:

~~~text
spans/day ≈ requests/sec × 86,400 × spans/request × retention_ratio
~~~

Illustrative capacity planning calculation:

~~~text
100 requests/sec
× 86,400 sec/day
× 8 spans/request
× 0.10
= 6,912,000 spans/day
~~~

This excludes background jobs, synthetic checks, retries, fan-out, or shifts in spans per request. Nor is it an invoice: real cost depends on domain tier, usage metering, service options, and current pricing.

After rollout, compare estimates against actual ingestion. If spans/request jumps severalfold after a minor change, audit instrumentation and app behavior before simply dialing down sampling.

### 9.3. Trimming Low-Value Telemetry

Options to weigh against investigation needs:

- Reduce or drop traces for high-frequency, low-value health checks.
- Keep operation names normalized, such as `GET /orders/{id}` rather than raw URLs carrying individual order IDs.
- Add attributes purposefully; avoid overly long values.
- Never use Trace ID, email, or order ID as metric dimensions.
- Establish ingestion and budget monitoring before expanding to additional services.

High cardinality makes data hard to query and metrics hard to aggregate, even when individual spans are small. Sampling rates should stay high enough to debug rare critical flows while fitting collection and retention budgets.

## 10. Security, Availability, and Controlled Rollout

### 10.1. Telemetry Is Governed Data Too

Audit what agents actually export:

| Risk source | Mitigation |
| --- | --- |
| Authorization headers, cookies, session tokens | Exclude from collected telemetry |
| Query strings, request bodies | Allowlist needed fields; avoid full-capture defaults |
| SQL text and exception messages | Audit for user data, literals, and secrets |
| Private Data Key | Restrict access, rotate keys, and update consumers |
| Cross-environment traces | Isolate domains or access scopes as needed |
| Externally supplied attributes | Bound allowed values, lengths, and trust |

Sampling reduces observation counts; it is not a data-sanitization control. If a private key leaks, rotate the key and scrub copies across configs, artifacts, and logs.

### 10.2. Measuring Overhead with Canary Rollouts

Before broad rollout:

1. Pick one service or a subset of replicas as a canary.
2. Record baseline latency, CPU, heap, and throughput under representative load.
3. Enable the agent with target settings, re-measure, and watch ingestion.
4. Verify cross-service traces, sensitive-data scrubbing, and rollback readiness.
5. Expand gradually while watching deltas between the canary group and the rest of the fleet.

Agent versions, sampler configs, and service identities belong in controlled deployment pipelines. Secrets should be injected separately through your platform's secret manager.

When telemetry backends slow down or become unreachable, the operational goal is protecting business traffic using bounded resources and timeouts. Never assume exporters buffer infinitely or guarantee zero span loss.

### 10.3. When Adding a Collector on OKE or Compute

A Collector centralizes endpoints and enforces uniform policies, yet adds an operational component you must run:

- Set CPU/memory requests/limits along with memory and queue bounds.
- Monitor refused/dropped telemetry and export failures.
- Configure bounded retries while accounting for potential data loss on restarts.
- Secure OTLP receiver endpoints inside the application network.
- If running multiple replicas with tail sampling, ensure Trace ID-aware routing.
- Test endpoint outage scenarios to measure app impact and data loss.

A healthy Collector does not guarantee complete traces: context may be missing in the app, an SDK may fail to export, or spans may drop before reaching the Collector.

## 11. Diagnosing Common Failures

| Symptom | Evidence-based checks |
| --- | --- |
| JVM fails to start after adding agent | JAR path, read permissions, flag syntax, version compatibility |
| App runs, no traces appear | Verify agent loaded; traffic exists; endpoint, key, exporter, sampling |
| Only one service appears | Library instrumentation on the other side, per-process config, region/domain |
| One request splits into multiple traces | Proxy stripped headers; mismatched propagators; lost context across async boundary |
| Inventory lacks `traceparent` in lab | Checkout's `-javaagent` flag, HTTP client support, `OTEL_PROPAGATORS` |
| HTTP 401/403 on export | Inspect actual response/logs; check key, domain, header, private/public path |
| HTTP 404 on export | Check hostname, OTLP path, missing or duplicated suffix |
| HTTP 429 or throttled telemetry | Check limits and ingestion metrics; tune volume/retries |
| TLS or timeout errors on export | DNS, routes, egress, proxy, certificates, JVM trust store |
| Spans exist with skewed timing | Clock sync, parent IDs, improperly started/ended spans |
| Error rate from traces differs from metrics | Sampling bias, request population, time window, one error spawning multiple spans |
| Sudden spike in span count | Dual agents/SDKs, duplicate instrumentation, retries, fan-out |

An HTTP status from the endpoint is just one clue. Read detailed error messages and rejection metrics before concluding root cause. When sharing support logs, scrub data keys and sensitive payloads.

If no traces appear in the lab, follow a simple diagnostic order:

~~~text
Is the app serving requests?
→ Did the agent initialize?
→ Is the agent creating spans?
→ Is the exporter sending and getting responses?
→ Are you viewing the right domain, region, and time window?
→ Is context connecting across both services?
~~~

## 12. Wrapping Up the Lab

Before tearing down the lab, save the verification artifacts from your run:

- Trace ID of a healthy request spanning both services.
- Slow trace illustrating the inventory wait gap.
- Error trace corresponding to `503` at inventory and `502` at checkout.
- JDK version, agent version, and sampling configuration (never save the private key).
- Span-based analysis: which step increased duration, where the error originated, and what further data would be needed.

Stop the JVMs with `Ctrl+C`. On shared lab hosts, clear key-bearing environment variables from your shell once processes exit:

~~~bash
unset OTEL_EXPORTER_OTLP_TRACES_HEADERS
unset APM_UPLOAD_BASE
~~~

If you created OCI resources strictly for this lab, clean up or stop them according to your environment's plan after saving required evidence. Check Compute, storage, and billable network components; having zero requests does not mean all charges have stopped.

The target outcome is being able to explain a request through its span relationships, recognize the boundaries of observed telemetry, and operate a trace pipeline into OCI APM with controlled access, volume, and resources.
