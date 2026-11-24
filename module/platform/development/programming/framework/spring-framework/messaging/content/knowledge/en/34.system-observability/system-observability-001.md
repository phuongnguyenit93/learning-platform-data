# Measuring Send/Receive Counts, Throughput, and Processing Duration

## Objectives

After this lesson, you can:

- Pinpoint exactly where in the lifecycle a message is counted as sent, received, successfully processed, or failed.
- Use Micrometer's Counter, Timer, Gauge, and DistributionSummary for their intended purposes.
- Calculate message/second and byte/second throughput from cumulative counters.
- Measure send duration, queue wait time, handler processing time, and end-to-end latency.
- Bring metrics and traces into Spring Boot using Micrometer Observation.
- Recognize built-in Spring Integration metrics and the limits of default instrumentation.
- Design low-cardinality tags and avoid overloading the metrics system.
- Test metrics to ensure measurements accurately reflect messaging behavior.

This lesson belongs to the **Spring Framework - messaging** topic, **System Observability** branch. The goal is to turn sending, receiving, and message processing activities into well-defined measurements to track load, detect errors, and identify causes of slowdowns.

## 1. Defining What Is Counted

Before creating a metric, you need to define the boundary of each event. In a messaging flow, a message can pass through several steps:

~~~text
Application creates message
        |
        v
Send attempt
        |
        v
Transport accepts / publish completes
        |
        v
Message is delivered to consumer
        |
        v
Handler starts
        |
        v
Handler succeeds or fails
        |
        v
Acknowledgement / reply / completion
~~~

These steps are not synonymous. For example, a send call returning successfully may only mean that the transport has accepted the data into a buffer; it does not necessarily prove that the broker has persisted it durably or that the consumer has finished processing it.

A useful set of counters can distinguish:

| Event | Meaning when the counter increments |
|---|---|
| send attempt | The application starts a send operation |
| send accepted | The transport/API confirms it has accepted the send operation according to its contract |
| send failed | The send call fails or is rejected |
| received | The message reaches the consumer/application boundary |
| processing started | The handler begins processing |
| processed | The handler completes successfully |
| processing failed | The handler terminates with an error |
| retried | A retry attempt is performed |
| redelivered | The consumer receives a previously delivered message again |
| dead-lettered | The message is routed to an error stream/DLQ |

Not every system needs all counters. Choose the events that answer specific operational questions. In particular, you must distinguish producer retries from broker redeliveries and internal handler retries.

A message may be sent twice but successfully processed only once thanks to deduplication. In that case, send count, receive count, and processed count differ; this difference can be correct behavior rather than necessarily a bug.

### 1.1. Defining the send and receive boundaries

For a producer, define what send accepted means:

- Did the API accept the request?
- Were the bytes written to the transport?
- Did the broker confirm the publish?
- Was the message durably persisted?

For a consumer, received can be when the message is handed to the callback, when the handler starts, or when the adapter finishes decoding. Choose a consistent boundary and document it clearly in the metric description.

With RSocket Request-Response, you can count outgoing requests and incoming responses separately. With Fire-and-Forget, there is no business response to confirm server-side processing; do not treat publisher completion as proof that server-side side effects have been committed.

## 2. Counter, Timer, Gauge, and DistributionSummary

Micrometer provides different meter types. Choosing the wrong type makes dashboards easy to misinterpret.

| Meter | Used to measure | Messaging examples |
|---|---|---|
| Counter | Cumulative event count, monotonically increasing | Number of successful sends, number of failed messages |
| Timer | Execution count and duration of each execution | Handler message processing duration |
| Gauge | Current value that can go up or down | Queue depth, number of in-flight requests |
| DistributionSummary | Distribution of a non-time quantity | Payload size in bytes |
| LongTaskTimer | Long-running tasks and active duration | Number of long-running flows/handlers currently executing |

### 2.1. Counter

A Counter is a cumulative count. It increases when an event occurs and does not decrease during the lifetime of a process. After an application restarts, the value in the new process starts over; the monitoring backend needs to handle counter resets.

Examples:

- app.messaging.messages with tags direction=outbound and result=accepted.
- app.messaging.messages with tags direction=inbound and result=processed.
- app.messaging.errors with tag stage=handler.

Do not use a Counter to represent the number of messages currently sitting in a queue. That value can increase and decrease, so you must use a Gauge or a queue metric provided by the adapter.

### 2.2. Timer

A Timer measures the duration of an operation and simultaneously records the measurement count. From a Timer you can obtain count, total time, max, and distribution statistics depending on registry configuration.

Timers should have clear boundaries:

- messaging.send: duration of the send/publish API execution.
- messaging.handler: duration of handler processing.
- messaging.end.to.end: from publish time to consumer completion, if suitable timestamps and correlation exist.
- messaging.queue.wait: time from when the broker receives the message to when the consumer starts processing, if the transport provides reliable timestamps.

Do not lump every time interval into a single timer. When latency increases, separate timers help pinpoint whether the time is spent at the producer, broker/queue, or consumer.

### 2.3. Gauge

A Gauge measures a value at the time of observation:

- Number of messages waiting in a queue.
- Number of handlers currently running.
- Number of in-flight requests.
- Number of remaining slots in a worker pool.
- Number of active connections.

A Gauge is not a counter. Do not sum gauge values over time to calculate total messages. For queue depth, a persistently high value is usually a sign that consumers are processing slower than the receive rate or that consumers have stopped.

### 2.4. DistributionSummary

DistributionSummary is suitable for payload size, batch size, or the number of items in a message. For example, record the byte count of each payload to observe median, p95, or size distribution.

If you need cumulative total bytes sent/received, use a separate Counter for total bytes. If you need the size distribution of individual messages, use a DistributionSummary. The two metrics answer different questions.

## 3. Calculating Message and Byte Throughput

**Throughput** is the amount of work completed per unit of time. For messaging, distinguish:

- Send throughput: number of messages accepted for sending per second.
- Receive throughput: number of messages arriving at the consumer per second.
- Processing throughput: number of messages the handler completes successfully per second.
- Failure rate: number of processing failures per second or failure ratio.
- Byte throughput: number of bytes sent/received per second.

If a counter records the total event count, average throughput over a window can be calculated as:

~~~text
throughput = (counter_end - counter_start) / elapsed_seconds
~~~

For example, if the processed counter increases from 12,000 to 15,000 in 60 seconds:

~~~text
(15,000 - 12,000) / 60 = 50 messages/second
~~~

In a monitoring system, use the backend's rate/increase functions instead of reading the counter manually each time. With Prometheus, for example:

~~~promql
sum(rate(app_messaging_messages_total{
  direction="inbound",
  result="processed"
}[1m]))
~~~

The result is the rate of successfully processed messages per second across all matching series.

To view the number of successful messages over 5 minutes:

~~~promql
sum(increase(app_messaging_messages_total{
  direction="inbound",
  result="processed"
}[5m]))
~~~

The actual Prometheus metric name depends on Micrometer's and the registry's naming conventions. Check the metrics endpoint before copying queries into a dashboard.

### 3.1. Messages/second and bytes/second

Message throughput does not fully reflect load if payload sizes vary widely. A system processing 1,000 small messages per second is different from one processing 1,000 5 MB messages per second.

Measure both:

- messages/second: number of messages crossing each boundary.
- bytes/second: total payload bytes or wire bytes crossing the chosen boundary.

Specify whether bytes are measured before or after serialization, and whether metadata/headers are included. If the producer measures object size while the consumer measures encoded bytes, the two metrics cannot be compared directly.

### 3.2. Reading throughput alongside queue depth

Decreasing throughput while queue depth increases usually suggests consumers cannot keep up with producers. Increasing throughput accompanied by rising processing latency may indicate the system is approaching resource limits.

A good dashboard should display at least:

- Send accepted rate.
- Receive rate.
- Processed rate.
- Failure rate.
- Queue depth and remaining capacity.
- Processing latency p50/p95/p99.

Seeing a high send rate alone does not prove the system is processing quickly. Messages may be accumulating at the broker or in a queue.

## 4. Measuring Processing Time and Latency

Processing time must be measured around the right lifecycle. A reactive handler can return a Mono immediately while the actual work only finishes later. If you only measure the method call that creates the Mono, the result will be artificially small and wrong.

Distinguish these intervals:

| Interval | Start | End |
|---|---|---|
| Send duration | Start of calling the send API | API/transport completes per contract |
| Queue wait | Broker receives message | Consumer starts processing |
| Handler duration | Handler starts | Handler completes/errors/cancels |
| End-to-end latency | Producer creates/publishes event | Consumer completes business logic |
| Acknowledgement latency | Consumer finishes processing | Broker/transport records ack if applicable |

### 4.1. Timer around a handler

For synchronous processing, Timer.record can wrap the business call. The Timer records both execution count and duration:

~~~java
Timer handlerTimer = Timer.builder("app.messaging.handler")
    .tag("operation", "process")
    .register(meterRegistry);

handlerTimer.record(() -> handler.handle(message));
~~~

If the handler throws an exception, the Timer still records the execution duration. A separate counter should record success/failure so dashboards can distinguish outcomes.

### 4.2. Measuring a reactive handler until completion

With Reactor, do not measure duration only from publisher creation. You can start a Timer.Sample when the publisher is subscribed to and stop it upon completion, error, or cancellation:

~~~java
Mono<Reply> process(Message<?> message) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return handler.handle(message)
            .doOnSuccess(reply -> processed.increment())
            .doOnError(error -> processingFailed.increment())
            .doFinally(signal -> sample.stop(handlerTimer));
    });
}
~~~

This example illustrates measuring a single subscribed publisher. The timer stops on terminal signals, including complete, error, and cancel. If cancellation needs to be analyzed separately, keep a counter for the CANCEL signal and use an appropriate outcome metric.

Depending on whether retry is placed inside or outside the measured boundary, the duration carries different meanings:

- A timer inside retry can record one sample per attempt.
- A timer outside retry measures total duration of the entire operation, including waits and retries.

Name and describe metrics according to the exact boundary being measured. Do not compare two timers with different semantics.

### 4.3. End-to-end latency and clock skew

If the producer records publishedAt and the consumer records processedAt, latency can be calculated from the two timestamps. However, two machines may have clock drift. For short latencies, clock skew of a few tens of milliseconds can significantly distort the numbers or make them negative.

To measure end-to-end latency:

- Synchronize clocks across hosts using a time synchronization mechanism.
- Use tracing to link producer and consumer.
- Prefer measuring duration within a single process when accurate timing of a segment is needed.
- Distinguish broker queue wait from handler duration.
- Do not treat arbitrary client-supplied timestamps as reliable milestones without validation.

Traces help follow a single message across multiple services. Metrics show overall trends; traces help locate where a specific request was slow.

## 5. Histograms, Percentiles, and SLAs

Average latency can hide very slow requests. For example, most messages process in 10 ms while a few take 5 seconds. The mean may look acceptable even while users are experiencing timeouts.

Track at least:

- p50: midpoint latency.
- p90/p95: latency below which most requests fall.
- p99: tail latency, sensitive to a small group of slow requests.
- max: largest sample in the observation window, useful but volatile.
- error rate: error ratio over total processed messages.

A Micrometer Timer can export histograms so the backend can compute aggregated percentiles. With Prometheus, you can use histogram_quantile:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_messaging_handler_seconds_bucket[5m])
  )
)
~~~

Metric names and units are normalized according to the registry; Timers are typically exported in seconds on Prometheus. Verify the actual name at the endpoint before using the query.

There are two common approaches:

- **Client-side percentiles:** compute percentiles inside each process. Easy to read locally, but percentiles across multiple instances cannot be accurately aggregated.
- **Histogram buckets:** send bucket counts so the backend aggregates them and computes percentiles. Suitable for distributed dashboards and comparing multiple instances.

Choose buckets around SLA thresholds. If the SLA is handler p95 under 200 ms, buckets need sufficient resolution around 200 ms. Do not generate hundreds of unnecessary buckets for every timer.

## 6. Micrometer Observation in Spring Boot

Spring Boot uses Micrometer Observation as an abstraction for metrics and traces. An Observation can produce meters and spans depending on the configured ObservationHandler.

Spring Boot can provide ObservationRegistry and MeterRegistry when the appropriate dependencies/auto-configuration are enabled. For business code, you can create custom observations:

~~~java
Observation.createNotStarted("messaging.process", observationRegistry)
    .lowCardinalityKeyValue("messaging.destination", "orders")
    .lowCardinalityKeyValue("messaging.operation", "handle")
    .observe(() -> orderHandler.handle(message));
~~~

This example measures a synchronous call. Low-cardinality key-values are included in metrics and traces. High-cardinality key-values such as messageId or customerId should only be used in traces when truly needed, and should not be placed into metric labels.

For reactive publishers, you must keep the observation alive until the terminal signal and ensure context is propagated through the Reactor pipeline. Do not use the synchronous example above to wrap a method returning a Mono and end the observation as soon as the publisher is created. If you need simple reactive duration measurement, Timer.Sample with Mono.defer and doFinally is a straightforward choice.

### 6.1. Default metrics have integration-specific limits

Not every Spring Messaging handler or RSocket endpoint automatically emits the same set of metrics. Check the adapter and integration you are using.

Spring Framework has built-in observations for some components such as HTTP, JMS publish/process, and scheduled tasks. For RSocket handlers or custom message flows, proactively instrument at send, receive, and processing boundaries, or use an integration with corresponding support.

If using Spring Integration, Micrometer metrics can be registered for components such as AbstractMessageChannel, AbstractMessageHandler, and AbstractMessageSource when a MeterRegistry is present. Traditional metric names include:

- spring.integration.send: timer for channel and handler send operations, with tags type, name, result, and exception.
- spring.integration.receive: counter for pollable channel and message source receive operations.
- spring.integration.channel.queue.size: gauge for QueueChannel size.
- spring.integration.channel.queue.remaining.capacity: gauge for QueueChannel remaining capacity.

Spring Integration since version 6 has Micrometer Observation support. Component instrumentation depends on IntegrationManagement, ObservationRegistry, and observationPatterns configuration; do not assume every component is enabled if unconfigured. Producer/handler/gateway observations have Spring Integration's own conventions and metrics.

These are Spring Integration metrics, not a guarantee that every plain Spring Framework MessageChannel or RSocket handler automatically has the same meters.

## 7. Designing Tags and Avoiding Cardinality Explosion

Tags help slice metrics by dimensions such as destination, operation, and result. However, each tag combination creates a meter series. If tag values are unbounded, the number of series can grow enormously.

Usually appropriate tags:

- operation: send, receive, process.
- destination: orders, payments, notifications if the list is finite.
- result: success, failure, rejected.
- transport: rsocket, jms, kafka if the set is small.
- exception: exception category or controlled simple class name.

Should not be used as metric tags:

- messageId, correlationId, traceId.
- userId, customerId, orderId.
- raw routes or destinations created arbitrarily by users.
- exception messages containing dynamic data.
- payload, email, or sensitive information.

Unique IDs are better suited for logs/traces with controlled sampling and retention. Metrics need analysis dimensions with a finite number of values.

Good tag example:

~~~text
destination=orders
operation=handle
result=failure
transport=rsocket
~~~

Bad tag example:

~~~text
messageId=evt-7f92...
customerId=customer-483920...
exceptionMessage=failed for order 123456...
~~~

## 8. Spring Boot Actuator and Exporting Metrics

A Spring Boot application typically uses Actuator and a Micrometer registry matching the monitoring backend.

Basic dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Use Spring Boot dependency management to select compatible versions. Do not pin Micrometer separately from the BOM without a specific reason.

Example endpoint configuration:

~~~properties
management.endpoints.web.exposure.include=health,metrics,prometheus
~~~

The /actuator/metrics endpoint lets you inspect meters by name and tag. The /actuator/prometheus endpoint provides the Prometheus exposition format if the registry and endpoint are configured. Management endpoints must be protected with appropriate network policies and authentication; do not expose all operational information publicly to the Internet.

A basic flow:

~~~text
Messaging handler
      |
      v
Micrometer Counter / Timer / Observation
      |
      v
MeterRegistry + ObservationRegistry
      |
      v
Prometheus registry / OTLP registry
      |
      v
Prometheus / metrics backend
      |
      v
Dashboard + alert
~~~

Metrics do not replace logs and traces. Metrics show trends such as dropping processing rate or rising p99; traces help find which message passed through which component and where it slowed down; logs provide error details and business context.

## 9. Java 17 Example: Measuring Send/Receive and Processing Duration

The following example uses Micrometer Core and SimpleMeterRegistry to simulate a message flow. In a Spring Boot application, replace SimpleMeterRegistry with the auto-configured or injected MeterRegistry.

### Maven dependency

In a Spring Boot project, use Boot's dependency management:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-core</artifactId>
</dependency>
~~~

### Source code

Save as **MessageMetricsDemo.java**:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.List;

public class MessageMetricsDemo {

    public static void main(String[] args) {
        MeterRegistry registry = new SimpleMeterRegistry();

        Counter sendAttempts = Counter.builder("demo.messaging.messages")
            .tag("direction", "outbound")
            .tag("result", "attempt")
            .register(registry);

        Counter sendAccepted = Counter.builder("demo.messaging.messages")
            .tag("direction", "outbound")
            .tag("result", "accepted")
            .register(registry);

        Counter received = Counter.builder("demo.messaging.messages")
            .tag("direction", "inbound")
            .tag("result", "received")
            .register(registry);

        Counter processed = Counter.builder("demo.messaging.messages")
            .tag("direction", "inbound")
            .tag("result", "processed")
            .register(registry);

        Counter processingFailed =
            Counter.builder("demo.messaging.messages")
                .tag("direction", "inbound")
                .tag("result", "failed")
                .register(registry);

        Timer handlerTimer = Timer.builder("demo.messaging.handler")
            .tag("handler", "orders")
            .register(registry);

        List<String> outgoing = List.of("order-1", "order-2");
        sendAttempts.increment(outgoing.size());
        sendAccepted.increment(outgoing.size());

        for (String message : outgoing) {
            received.increment();

            Timer.Sample sample = Timer.start(registry);
            try {
                handle(message);
                processed.increment();
            } catch (IllegalArgumentException ex) {
                processingFailed.increment();
            } finally {
                sample.stop(handlerTimer);
            }
        }

        System.out.println("send-attempts=" + (long) sendAttempts.count());
        System.out.println("send-accepted=" + (long) sendAccepted.count());
        System.out.println("received=" + (long) received.count());
        System.out.println("processed=" + (long) processed.count());
        System.out.println(
            "processing-failed=" + (long) processingFailed.count()
        );
        System.out.println("processing-samples=" + handlerTimer.count());

        registry.close();
    }

    private static void handle(String message) {
        if ("order-2".equals(message)) {
            throw new IllegalArgumentException("Invalid test message");
        }
    }
}
~~~

### Compile and run

~~~bash
javac -cp micrometer-core.jar MessageMetricsDemo.java
java -cp .;micrometer-core.jar MessageMetricsDemo
~~~

The two commands above illustrate how to run when micrometer-core.jar and its transitive dependencies are already on the classpath. In a real Maven/Gradle project, letting the build tool manage dependencies is more convenient.

Exact output:

~~~text
send-attempts=2
send-accepted=2
received=2
processed=1
processing-failed=1
processing-samples=2
~~~

The Timer records two executions, including one success and one error. The counters report the business outcomes. The example uses SimpleMeterRegistry for in-memory inspection; a production registry can export data to Prometheus or another backend.

## 10. What Questions Should Dashboards and Alerts Answer?

A messaging dashboard should help operators answer these questions:

**Can the producer send?**
- Send attempts and send accepted rate.
- Send failures by result/exception.
- Send duration p95.

**Is the consumer receiving and processing fast enough?**
- Receive rate and processed rate.
- Processing failures and retries/redeliveries.
- Handler duration p50/p95/p99.
- Queue depth and active handler count.

**Is the system bottlenecked?**
- Queue depth increasing continuously.
- Processed rate lower than receive rate over a sufficiently long interval.
- In-flight requests increasing.
- p95/p99 increasing while throughput does not increase proportionally.
- Worker pool or connection pool running out of capacity.

**Is it a business issue or an infrastructure issue?**
- Validation/conflict errors vs. timeouts or connection errors.
- A specific destination failing vs. the whole system.
- Inactive consumer vs. active consumer processing slowly.

Alerts should be based on time windows and thresholds appropriate for the workload. Do not alert solely because of a single high p99 sample in a window with very few messages. Combine latency with traffic volume and error rate to reduce noisy alerts.

## 11. Testing Metrics

Metrics are also part of application behavior and need to be tested.

Useful tests:

1. Send one message successfully; send accepted and processed counters increment by exactly one.
2. Send fails; failure counter increments while accepted does not.
3. Handler throws an exception; processing Timer still records one sample and failure counter increments.
4. Reactive handler is cancelled; timer stops and cancellation is categorized separately if needed.
5. A message is retried; attempt count increments by the number of attempts, while business success increments only for successful operations.
6. A message is redelivered; receive/redelivery count accurately reflects adapter policy.
7. A message is deduplicated; receive count may increment while business processed count does not increment further.
8. Timer is measured until the terminal signal, not stopped as soon as the publisher is created.
9. Tags only use finite values; messageId does not create a separate meter.
10. Prometheus scrape displays metric names, units, and labels matching what the dashboard uses.

For tests with SimpleMeterRegistry, you can verify count and totalTime using the Micrometer API. For integration tests, verify which meters the real adapter actually emits rather than assuming every transport has the same semantics.

## 12. Common Mistakes

- Counting a send API call as if the broker had durably persisted the message.
- Counting message received as if the handler had processed it successfully.
- Using a Gauge for cumulative total message counts.
- Using a Counter for current queue depth.
- Calculating throughput from absolute counter values without considering elapsed time and resets.
- Tracking only average latency while ignoring p95/p99.
- Measuring the method call returning a Mono instead of the publisher completion time.
- Mixing queue wait, handler duration, and end-to-end latency into one timer.
- Failing to distinguish retries, redeliveries, and successful processing.
- Putting messageId/userId into tags, causing unbounded cardinality growth.
- Assuming every Spring Messaging/RSocket handler has automatic metrics.
- Enabling instrumentation in both the framework and custom code without checking for duplicate observations.
- Using the same metric name for two different measurement boundaries.

## 13. Implementation Checklist

- [ ] Send attempt, send accepted, receive, processed, and failed are clearly defined.
- [ ] Retry/redelivery/deduplication are counted separately when needed.
- [ ] Counter is used for cumulative events; Gauge is used for current values.
- [ ] Timers wrap the exact processing boundary.
- [ ] Reactive timers stop on complete/error/cancel.
- [ ] Both message/second and byte/second throughput are available.
- [ ] Processing latency p50/p95/p99 and error rate are tracked.
- [ ] Queue depth and in-flight work are observed.
- [ ] Tags have low cardinality and contain no unique IDs or payloads.
- [ ] Micrometer Observation/Tracing is configured at boundaries that need tracking.
- [ ] Default transport/integration metrics have been verified.
- [ ] Tests exist for success, failure, retry, redelivery, and cancellation.
- [ ] Dashboards and alerts use accurate metric semantics.

## Conclusion

Effective messaging measurement starts with accurately defining a send, receive, and process. Counters report event counts; Timers measure duration and latency distributions; Gauges report queue/in-flight state. Throughput must be computed from counter increase rates, while p95/p99 reveal tail latency that averages hide. Micrometer and Spring Boot provide the observability foundation; custom RSocket/message handlers need to be instrumented according to their actual lifecycle, while Spring Integration has its own per-component and configuration-driven metrics/observations.

## References

- [Spring Boot Reference - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference - Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework Reference - Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Integration Reference - Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Micrometer Reference - Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html)
- [Micrometer Reference - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Prometheus Documentation - Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/)
