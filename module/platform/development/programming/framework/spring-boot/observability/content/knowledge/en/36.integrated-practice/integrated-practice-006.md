# Configuring Sampling

Sampling decides which traces are retained for investigation. In a Spring Boot system with multiple services, sampling must balance error-finding capability, trace detail, storage cost, and load on the collector. If the sampling rate is too low, error traces may be lost; if you sample 100% in high-traffic production, costs and pipeline pressure can surge sharply.

This practice exercise configures sampling for a checkout flow calling payment, then checks trace context across service boundaries. The final part extends to tail sampling at the OpenTelemetry Collector to prioritize traces with errors or high latency.

## Objectives

Upon completion, you will be able to:

- Distinguish head sampling from tail sampling.
- Configure sampling probability in Spring Boot using Micrometer Tracing.
- Choose different rates for local, test, and production environments.
- Verify that downstream services honor the parent trace's sampling decision.
- Understand why sampling traces does not mean reducing metrics or logs.
- Evaluate trade-offs across cost, coverage, and investigability.

## Practice Context

Suppose the system has two services:

~~~text
Client
  |
  v
checkout-service
  |
  | HTTP + trace context
  v
payment-service
  |
  v
Payment provider
~~~

checkout-service receives a request, creates a server span, and calls payment-service via an instrumented HTTP client. payment-service creates a server span belonging to the same trace, and may then create a span for calling the payment provider.

When sampling is enabled, the decision to keep a trace is usually made at the start of the trace. Downstream services must continue the context and honor the sampling decision propagated in the trace context. If every service sampled independently, a trace might retain only fragmented segments and become very hard to analyze.

## 1. Preparing Tracing in Spring Boot

With Spring Boot 3.x, Micrometer Observation and Micrometer Tracing provide the integration point for tracing. The application needs Actuator, a tracing bridge, and an exporter matching the backend.

Example Maven dependencies for the OpenTelemetry path:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Use Spring Boot's dependency management to manage compatible versions. If choosing the Brave bridge, use micrometer-tracing-bridge-brave instead of the OpenTelemetry bridge. Each application should choose only one tracing bridge as its primary integration mechanism. Exact exporter declarations depend on the Spring Boot version and pipeline in use.

Adding dependencies alone does not prove traces are exported. Verify that the application has an exporter, collector endpoint, and proper resource identity before evaluating sampling.

## 2. Configuring Probability-Based Head Sampling

Head sampling makes its decision when the trace starts. With Micrometer Tracing auto-configured by Spring Boot, probability can be set via management.tracing.sampling.probability.

~~~yaml
# application.yml
spring:
  application:
    name: checkout-service

management:
  tracing:
    sampling:
      probability: 0.10
~~~

A value of 0.10 means aiming to sample roughly 10% of root traces using the probabilistic sampler. This is an illustrative starting value; production rates must be based on traffic, spans per trace, exporter capacity, and investigation requirements.

Apply a corresponding configuration for payment-service. Each service may have its own resource identity, but a trace's sampling decision must be propagated across services. When using a parent-based sampler, child services follow the parent's sampled flag instead of rolling the dice again for each span.

You can separate rates by profile:

~~~yaml
# application-local.yml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

~~~yaml
# application-prod.yml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Locally, 1.0 enables full visibility into test flows. A rate of 0.05 in production is only an example; tune it based on traffic, trace length, and storage budget. Avoid pushing 1.0 to production merely for debugging convenience.

You can use an environment variable to control the rate at deployment time:

~~~text
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.05
~~~

Verify which profile is active and the final resolved value Spring Boot receives. A profile file has no effect if that profile is not activated.

### Understanding the Sampled Flag

With W3C Trace Context, the traceparent header contains the trace ID, parent span ID, and trace flags. The sampled bit in trace flags indicates the sampling decision according to the W3C specification.

Example:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

The trailing flags value is 01 in this example, indicating the trace is marked sampled. The receiving service uses a propagator to extract the context and create a child span within the existing trace. Do not rewrite traceparent with an arbitrary filter, and do not generate a new trace ID when a valid context already exists.

If the system uses multiple libraries or agents, verify that all of them use compatible propagators and tracing pipelines. Header names, trace IDs, and the sampled flag must be preserved across HTTP clients, gateways, and message brokers.

## 3. Preserving the Sampling Decision Across Services

Configuring a rate per service is not enough. You must verify how the sampler handles traces that already have a parent context.

For a request passing through checkout-service and payment-service, the expectation is:

- If checkout creates a sampled trace, payment continues that trace and exports its own spans.
- If checkout creates an unsampled trace, payment does not start an independent trace for the same request just because payment's local rate is higher.
- If no valid trace context is present, the receiving service may start a new trace and apply its own root sampler.

Spring Boot auto-instrumentation for properly configured clients normally injects context automatically. Example using RestClient.Builder provided by Spring Boot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class PaymentClientConfiguration {

    @Bean
    RestClient paymentClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://payment-service")
                .build();
    }
}
~~~

Use the builder configured by the framework so application customizers and instrumentation are applied. If you instantiate a client independently or use an uninstrumented HTTP library, trace context may not be propagated. For WebClient, RestTemplate, or other clients, verify the integration corresponding to the version you are running.

With message brokers, the producer must inject trace context into message headers and the consumer must extract the context before processing. If offloading work to an executor or scheduler, use an appropriate context propagation mechanism; ThreadLocal does not automatically preserve context after switching threads.

## 4. Verifying Sampling with a Test Scenario

Do not glance at a dashboard and assume the sampling rate is right. Run the same request flow across both services and inspect both retained traces and dropped traces.

### Local Verification at 100% Sampling

1. Activate the local profile on both checkout-service and payment-service.
2. Confirm both services export telemetry to the same test backend or collector.
3. Send several test requests flowing through checkout to payment.
4. Open the trace in the backend and locate two server spans sharing the same trace ID and a proper parent-child relationship.
5. Verify checkout's client span describes the HTTP call to payment.
6. Check that resource service.name distinguishes checkout-service and payment-service.

At sampling 1.0, root traces in the test scope should be retained, unless another layer is filtering or the exporter is failing. If you only see spans in checkout, check context propagation and payment's exporter configuration before concluding the sampler is wrong.

### Local Verification at 0% Sampling

Temporarily set probability to 0 in the local or test environment, then send new requests. Do not reuse a trace created before changing configuration.

Expectations:

- No new traces are exported by the head sampler at rate 0.
- Business requests still run normally.
- Metrics such as request count and request duration are still recorded if the meter pipeline is active.
- Logs are still written per logging configuration; logs may still carry a trace ID even though the backend does not necessarily store a corresponding trace.

Sampling traces is a decision for the tracing pipeline. It does not automatically reduce metrics or logs. If metrics or logs vanish along with traces, inspect exporter configurations and filters specific to those signals.

### Verifying Propagation Between Services

You can send a request with a known valid traceparent and check whether the trace ID is preserved across checkout and payment. Use one context marked sampled and one context not sampled to test both branches.

When testing, do not merely compare total trace counts. Verify:

- Trace IDs in checkout and payment are identical.
- Span IDs differ across spans.
- The parent span ID of payment's server span links properly to checkout's client span according to the instrumentation model.
- The sampled decision is honored.
- No detached new trace is created for the same request.
- Requests do not fail simply because a trace is dropped.

A probabilistic rate gives no exact guarantee on tiny batches. If you send 10 requests at a 10% rate, the result might be 0, 1, 2, or more retained traces. Use a large enough request count to observe trends and verify deterministic behavior using known test contexts.

## 5. Choosing a Rate Based on Traffic and Cost

An initial estimate is:

~~~text
Retained traces per second
    = Root traces per second x Sampling probability

Exported spans per second
    = Retained traces per second x Average spans per trace
~~~

For example, a system with 200 root requests per second, averaging 8 spans per trace:

| Sampling probability | Retained traces per second | Exported spans per second |
|---:|---:|---:|
| 1.00 (100%) | 200 | 1,600 |
| 0.10 (10%) | 20 | 160 |
| 0.05 (5%) | 10 | 80 |
| 0.01 (1%) | 2 | 16 |

This is a simplified estimate assuming each request creates one root trace and average span count stays constant. Retries, fan-out, message consumers, and deep traces can make actual span counts higher. Span size, batching, queues, and retention duration must also be factored in.

When choosing a rate, consider:

- Peak-hour request volume and number of services per trace.
- Error rate and error reproducibility.
- Network, collector, backend capacity, and retention.
- Level of detail needed to investigate latency.
- Sensitive data and access control requirements.
- Ability to raise sampling in a controlled way during an incident.

Never pick a rate solely based on development traffic. Production requires load measurement and monitoring of dropped spans.

## 6. When Is Tail Sampling Needed?

Head sampling decides early, before knowing whether a request will fail or run slowly. Consequently, an error trace can be dropped if the initial root decision was unsampled.

Tail sampling defers the decision until the collector has received the trace's spans. The collector can retain traces matching conditions such as:

- Traces containing a span with status ERROR.
- Traces with latency exceeding a threshold.
- Critical operations that require frequent observation.
- A small percentage of normal traces as a baseline.

Tail sampling fits when you need to prioritize traces with high investigative value. In return, the collector must buffer trace state in memory during the wait window, receive all related spans, and be provisioned with sufficient resources.

### Example Tail Sampling Configuration in OpenTelemetry Collector

The following snippet illustrates a simple traces pipeline. Component names and processor capabilities depend on your OpenTelemetry Collector distribution; verify that the tail_sampling processor is included in your build.

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      - name: keep-slow-traces
        type: latency
        latency:
          threshold_ms: 1000

      - name: keep-baseline
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

  batch:

exporters:
  otlp:
    endpoint: tempo:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp]
~~~

The numbers above are only examples for a test environment. num_traces, expected_new_traces_per_sec, and decision_wait must be sized according to trace rate, span count, payload size, and request completion time. Insecure TLS is only suitable for lab examples in a test network; real environments require proper TLS and authentication.

In this example, the policy keeps error traces, slow traces, and a percentage of baseline traces. Tail sampling cannot retain a trace the collector never received. If the application SDK already dropped that trace via head sampling, the collector cannot recover discarded spans. When using tail sampling to select based on errors or latency, configure upstream to send enough traces to the collector; this can increase network traffic between applications and the collector.

In a collector cluster, all spans of the same trace must be routed to the same tail sampler instance. If spans of a single trace are split across independent collectors, each sees only part of the trace and can make wrong decisions. Multi-collector architectures typically require a load-balancing layer routing by trace ID and handling instance failures.

Tail sampling does not replace head sampling in every scenario either. It fits when you have sufficient collector capacity and need outcome-based selection; head sampling fits when you need early load shedding and a simpler pipeline.

## 7. Keeping Metrics and Logs Useful When Reducing Traces

Trace sampling should not blind you to overall service health. Metrics normally still record every request per meter configuration regardless of whether a trace was sampled. Thus, latency, throughput, and error rate dashboards still reflect total traffic.

Logs are also a separate pipeline. A log emitted inside an unsampled trace may still contain the active trace ID and span ID. When searching logs by trace ID and finding no trace, understand that the trace may have been dropped by sampling or lost at the exporter/collector. Distinguish these two cases by monitoring sampler and pipeline status.

Do not put trace IDs into metric labels to compensate for sampling; doing so creates extremely high cardinality. If your backend supports exemplars, use exemplars to link a metric observation to a sample trace.

## 8. Operating and Changing Sampling Safely

Sampling is an operational setting with direct impact on cost and investigability. When changing rates:

1. Record current rates by environment and service.
2. Estimate the number of traces/spans that will be sent at peak traffic.
3. Apply the change in a test environment first and verify propagation.
4. Roll out per service or traffic slice if the architecture allows.
5. Monitor exporter queues, collector memory, export errors, and dropped spans.
6. Compare trace coverage before and after the change.
7. Document the timestamp, reason, owner, and rollback procedure.

Do not change sampling abruptly across the whole system without knowing whether collectors can handle the increased load. If you need to increase sampling during an incident, set a time limit and criteria for returning the rate to normal once the investigation concludes.

Indicators to monitor include spans created, spans exported, spans dropped, queue utilization, export failures, collector memory, and telemetry pipeline latency. Exact metric names depend on the SDK, exporter, and collector; use the actual metrics of your deployed versions.

## 9. Common Issues and Troubleshooting

| Symptom | Possible Causes | How to Check |
|---|---|---|
| No traces visible at all | Probability is 0, exporter not configured, or wrong endpoint | Check active profile, resolved property, exporter, and collector logs |
| Only spans in the first service appear | Client does not inject context or downstream service does not extract | Check builder, instrumentation, and traceparent |
| Trace splits into multiple trace IDs | Context lost or replaced at a boundary | Check HTTP headers, message headers, and async context |
| Child service ignores sampled flag | Sampler or bridge does not handle parent context as expected | Check bridge type, sampler, and parent-based configuration |
| Error traces do not appear | Head sampling dropped the trace before the error occurred | Consider tail sampling and how traces are forwarded to the collector |
| Metrics drop alongside traces | Unexpected filter or pipeline coupling | Check meter registry and metrics exporter independently |
| Collector drops spans | Full queue, insufficient memory, or overloaded tail sampler | Check throughput, queue, memory, and decision wait |
| Trace missing spans in a tail-sampling cluster | Spans of the same trace land on different collectors | Check trace-ID-based load balancing |

## Self-Check Exercises

1. Set sampling to 1.0 for local. Send a request across two services and verify spans share the same trace.
2. Set sampling to 0.0. Send new requests and verify metrics still increment while new traces are not exported.
3. Set sampling to 0.1. Send a sufficiently large batch of requests and compare retained trace ratio with statistical expectations.
4. Send a known traceparent with the sampled flag enabled and disabled. Verify downstream services honor the parent context.
5. Enable tail sampling in a test collector. Trigger one error request, one slow request, and multiple normal requests; verify policies retain the intended traces.
6. Shut down the collector briefly. Verify business requests continue working and the exporter/collector reports errors or drops.

A sampling configuration meets requirements when decisions propagate consistently across services, traces are retained according to policy, metrics and logs remain independently valuable, and the pipeline has enough capacity to handle telemetry traffic. Document rates per environment, configuration owners, and procedures for raising/lowering sampling so production investigations can be carried out safely.
