# Adding Metrics and Message History

## 1. Practice Objectives

In the **Comprehensive Practice** chapter of **SPRING_INTEGRATION_CORE**, this lesson adds observability to an order-processing flow written in the Java DSL. The flow uses `Message`, `MessageChannel`, a transformer, a service activator, and a gateway; from there, it answers three questions:

- How many requests did the system process, how many failed, and how long did they take?
- Which components did a specific message pass through before succeeding or failing?
- When an abnormal metric appears, which data should be inspected to find the root cause?

After this lesson, you will be able to enable metrics for integration components, add well-scoped business metrics, read message history at the output and at failure points, and write tests confirming those signals.

**Example API baseline:** Java 17+, Spring Boot 3.5.x, and Spring Integration 6.5.x. Let Spring Boot's BOM manage dependency versions; this is a baseline to reproduce the lesson, not a claim about the latest version. The main configuration uses Micrometer metrics directly; the Observation section is presented separately so you can recognize meter name changes.

## 2. Picking the Right Signal for the Question

| Signal | Appropriate question | Data in this lesson |
| --- | --- | --- |
| Metrics | Over a time window, is the flow behaving normally? | Send success/failure counts, processing latency, accepted order count |
| Message history | Where did the message under inspection travel? | Component name, component type, timestamp in the `history` header |
| Contextual logs | What happened in a specific execution? | `requestId`, exception type, list of component names |
| Distributed tracing | Where did a request crossing multiple services spend time? | Traces/spans and context propagation across processes |

Message history travels with a message, making it very helpful when investigating a specific case. To see trends across thousands of messages, use metrics. To correlate events belonging to the same request, this lesson uses the `requestId` header; do not put this value into a meter tag.

### 2.1. Counter, Timer, and Gauge

- **Counter:** cumulative event count, such as how many times the business accepted an order.
- **Timer:** measurement count and total duration, optionally with distribution statistics. Display units depend on the backend; when reading from Java, specify `TimeUnit`.
- **Gauge:** value at observation time, such as how many messages currently sit in a queue.

A `Timer` already tracks a count, so do not add a separate counter solely to count the same calls measured by the timer. The business counters in this lesson have distinct semantics: separating order acceptance decisions from framework message sends. See [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

### 2.2. Defining Scope Before Naming

This lesson uses two classes of metrics:

| Metric | Scope |
| --- | --- |
| `spring.integration.send` | Sending to a channel or invoking a handler, distinguished by tags |
| `orders.accepted` | Number of times `OrderProcessor.process()` returns an accepted result |
| `orders.failed` | Number of times `OrderProcessor.process()` throws `RuntimeException` |
| `orders.processing` | Duration inside `OrderProcessor.process()`, split by `outcome` |

If the transformer fails before invoking the processor, `orders.failed` does not increment. If the processor returns normally yet forwarding the result to the next channel fails, `orders.accepted` has already incremented. This is a consequence of the chosen measurement scope; this counter does not confirm a database commit or successful delivery.

## 3. The Flow to Observe

~~~mermaid
flowchart LR
    A["OrdersGateway or MessageChannel.send"]
    B["orders.input / DirectChannel"]
    C["orders.normalize / Transformer"]
    D["orders.normalized / DirectChannel"]
    E["orders.process / Service Activator"]
    F["orders.completed / QueueChannel"]
    G["Consumer reads result"]

    A --> B --> C --> D --> E --> F --> G
    E -. "SKU = FAIL: throws exception" .-> X["Caller receives error"]
~~~

Two `DirectChannel` beans keep processing on the caller thread. The `QueueChannel` at the end holds results for a consumer to read later; the queue does not create a processing thread on its own.

Naming conventions in this lesson:

- Gateway: `ordersGateway`.
- Channels: `orders.input`, `orders.normalized`, `orders.completed`.
- DSL endpoints: `orders.normalize`, `orders.process`.

Clear naming helps connect meters, logs, history, and flow configuration. An endpoint and the handler inside that endpoint are distinct objects; handler names may carry DSL-generated suffixes. When writing stable assertions, this lesson prefers explicitly declared channel names.

## 4. Preparing Dependencies and Metrics Endpoints

In a project already using the Spring Boot 3.5.x parent/BOM, add the following dependencies to `pom.xml`. This is the dependencies snippet, not the full POM.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Spring Boot auto-configures `MeterRegistry` based on registry implementations on the classpath. With the Prometheus dependency, the application can export metrics via its endpoint; do not add an extra `SimpleMeterRegistry` in the main application configuration. That registry is used only in standalone tests later on. See [Spring Boot Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html).

Local run configuration in `application.yml`:

~~~yaml
spring:
  application:
    name: integration-observability-lab

server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
  metrics:
    tags:
      application: integration-observability-lab
    distribution:
      percentiles-histogram:
        orders.processing: true
~~~

The loopback address is appropriate for a lab on a personal machine. If moving configuration to a deployed environment, configure Actuator access permissions according to that environment's infrastructure.

`/actuator/metrics` serves to explore meters and tags; `/actuator/prometheus` provides the format for Prometheus to scrape. Whether a registry exists and whether an endpoint is exposed over HTTP are two separate conditions. See [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html).

## 5. Implementing the Gateway, Flow, and Business Metrics

The illustrative classes use package `example.integration.metrics`. Place the files under the corresponding Java source root of your practice project.

### 5.1. Gateway

File `OrdersGateway.java`:

~~~java
package example.integration.metrics;

import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.Message;

@MessagingGateway(
        name = "ordersGateway",
        defaultRequestChannel = "orders.input")
public interface OrdersGateway {

    void submit(Message<OrdersFlowConfig.OrderRequest> request);
}
~~~

The gateway has a `void` return type: the caller does not wait to receive a reply payload from the gateway. Results are explicitly routed by the flow into `orders.completed`.

**`void` does not mean asynchronous.** In this configuration, the caller still executes the transformer and processor through `DirectChannel`. Changing a Java return type does not create an executor or poller. See [Messaging Gateways](https://docs.spring.io/spring-integration/reference/6.5/gateway.html).

### 5.2. Flow Configuration

File `OrdersFlowConfig.java`:

~~~java
package example.integration.metrics;

import java.util.Locale;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationManagement;
import org.springframework.integration.config.EnableMessageHistory;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
@EnableIntegrationManagement
@EnableMessageHistory({"ordersGateway", "orders.*"})
@IntegrationComponentScan(basePackageClasses = OrdersGateway.class)
public class OrdersFlowConfig {

    public record OrderRequest(String orderId, String sku, int quantity) {
    }

    public record OrderResult(
            String orderId, String sku, int quantity, String status) {
    }

    @Bean("orders.input")
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean("orders.normalized")
    public DirectChannel ordersNormalized() {
        return new DirectChannel();
    }

    @Bean("orders.completed")
    public QueueChannel ordersCompleted() {
        return new QueueChannel(100);
    }

    @Bean
    public OrderProcessor orderProcessor(MeterRegistry registry) {
        return new OrderProcessor(registry);
    }

    @Bean
    public IntegrationFlow ordersFlow(OrderProcessor processor) {
        return IntegrationFlow.from("orders.input")
                .transform(OrderRequest.class,
                        request -> new OrderRequest(
                                request.orderId(),
                                request.sku().strip().toUpperCase(Locale.ROOT),
                                request.quantity()),
                        endpoint -> endpoint.id("orders.normalize"))
                .channel("orders.normalized")
                .handle(processor, "process",
                        endpoint -> endpoint.id("orders.process"))
                .channel("orders.completed")
                .get();
    }

    public static class OrderProcessor {

        private final MeterRegistry registry;
        private final Counter accepted;
        private final Counter failed;
        private final Timer successTimer;
        private final Timer failureTimer;

        public OrderProcessor(MeterRegistry registry) {
            this.registry = registry;
            this.accepted = Counter.builder("orders.accepted")
                    .description("Orders accepted by the processor")
                    .register(registry);
            this.failed = Counter.builder("orders.failed")
                    .description("Failed processor invocations")
                    .register(registry);
            this.successTimer = Timer.builder("orders.processing")
                    .tag("outcome", "success")
                    .register(registry);
            this.failureTimer = Timer.builder("orders.processing")
                    .tag("outcome", "failure")
                    .register(registry);
        }

        public OrderResult process(OrderRequest request) {
            Timer.Sample sample = Timer.start(this.registry);
            boolean success = false;

            try {
                if (request.quantity() <= 0) {
                    throw new IllegalArgumentException(
                            "Quantity must be greater than zero");
                }

                if ("FAIL".equals(request.sku())) {
                    throw new IllegalStateException(
                            "Simulated processor failure");
                }

                OrderResult result = new OrderResult(
                        request.orderId(),
                        request.sku(),
                        request.quantity(),
                        "ACCEPTED");

                this.accepted.increment();
                success = true;
                return result;
            }
            catch (RuntimeException ex) {
                this.failed.increment();
                throw ex;
            }
            finally {
                sample.stop(success ? this.successTimer : this.failureTimer);
            }
        }
    }
}
~~~

Configuration decisions:

1. `@EnableIntegration` registers integration infrastructure, allowing the same configuration to work both with Spring Boot and in minimal test contexts.
2. `@EnableIntegrationManagement` enables management configuration; since `observationPatterns` is not passed, Micrometer meters are used directly for components.
3. `@EnableMessageHistory` restricts tracked components by name. Declare only one message history configuration per application context.
4. `@IntegrationComponentScan` discovers `@MessagingGateway` interfaces. This explicit configuration also takes effect in test contexts that do not boot a full Boot application.
5. The handler returns an `OrderResult` payload. The framework builds the reply message and propagates appropriate headers; the example avoids manually creating a `GenericMessage` that would drop input context.
6. Timers and counters are registered once in the constructor, avoiding recreating builders on the per-message hot path.

The role of `@IntegrationComponentScan` for gateway interfaces is described in [Annotation Support](https://docs.spring.io/spring-integration/reference/6.5/configuration/annotations.html). Chained flow declarations are covered in [Java DSL Basics](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

`QueueChannel(100)` places a capacity bound on stored results. The demo puts in only two results and reads them out; sending continuously without a consumer can fill the queue and block result sends. Queue bounds do not create retry or overload-shedding policies automatically.

## 6. Reading History and Generating Sample Traffic

### 6.1. Reading Component Names from Headers

File `HistorySupport.java`:

~~~java
package example.integration.metrics;

import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;

public final class HistorySupport {

    private HistorySupport() {
    }

    public static List<String> names(Message<?> message) {
        if (message == null) {
            return List.of();
        }

        MessageHistory history = message.getHeaders()
                .get(MessageHistory.HEADER_NAME, MessageHistory.class);

        if (history == null) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        for (Properties entry : history) {
            result.add(entry.getProperty("name"));
        }
        return List.copyOf(result);
    }

    public static Message<?> failedMessage(Throwable failure) {
        Throwable current = failure;
        while (current != null) {
            if (current instanceof MessagingException messagingException
                    && messagingException.getFailedMessage() != null) {
                return messagingException.getFailedMessage();
            }
            current = current.getCause();
        }
        return null;
    }
}
~~~

The `history` header holds a `MessageHistory` whose `Properties` entries include details such as `name`, `type`, and `timestamp`. The helper above merely copies names into a `List<String>` for logging and assertions; it does not modify history entries. Pattern configuration and reading the header are presented in [Message History](https://docs.spring.io/spring-integration/reference/6.5/message-history.html).

### 6.2. Running the Demo with Two Success Requests and One Failure Request

File `DemoApplication.java`:

~~~java
package example.integration.metrics;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
public class DemoApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DemoApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner exercise(
            OrdersGateway gateway,
            @Qualifier("orders.input") MessageChannel input,
            @Qualifier("orders.completed") QueueChannel completed) {

        return args -> {
            gateway.submit(request("O-101", " book ", 2, "req-101"));
            gateway.submit(request("O-102", " pen ", 3, "req-102"));

            try {
                input.send(request("O-103", " fail ", 1, "req-103"));
            }
            catch (RuntimeException ex) {
                Message<?> failed = HistorySupport.failedMessage(ex);
                log.warn("order_failure requestId={} exception={} path={}",
                        failed == null
                                ? "unknown"
                                : failed.getHeaders().get("requestId"),
                        ex.getClass().getSimpleName(),
                        HistorySupport.names(failed));
            }

            for (int i = 0; i < 2; i++) {
                Message<?> result = completed.receive(1000);
                if (result == null) {
                    throw new IllegalStateException(
                            "Expected a completed order");
                }

                log.info("order_completed requestId={} result={} path={}",
                        result.getHeaders().get("requestId"),
                        result.getPayload(),
                        HistorySupport.names(result));
            }
        };
    }

    private static Message<OrdersFlowConfig.OrderRequest> request(
            String orderId, String sku, int quantity, String requestId) {

        return MessageBuilder.withPayload(
                        new OrdersFlowConfig.OrderRequest(
                                orderId, sku, quantity))
                .setHeader("requestId", requestId)
                .build();
    }
}
~~~

The failure branch intentionally calls `MessageChannel.send()` to keep inspecting `MessagingException.getFailedMessage()` straightforward. A gateway may unwrap exception layers when propagating errors back to the caller; do not assume every exception received by a gateway caller still carries the failed message.

In a synchronous flow, exceptions from a handler can propagate back to the caller. Having an `errorChannel` bean does not automatically route all synchronous errors there. For asynchronous tasks or pollers, examine `ErrorMessage` publication and configure the corresponding error channel. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

After running the demo once in a fresh process, the expected observations are:

| Observation | Expected value |
| --- | --- |
| Business results | `O-101/BOOK/2/ACCEPTED` and `O-102/PEN/3/ACCEPTED` |
| `orders.accepted` | `2` |
| `orders.failed` | `1` |
| Count of `orders.processing{outcome=success}` | `2` |
| Count of `orders.processing{outcome=failure}` | `1` |
| Messages remaining in `orders.completed` after reading | `0` |

These are results to reproduce during practice, not benchmark measurements. Rerunning the application creates a fresh process and registry; inspect counters per run.

## 7. Exploring and Interpreting Metrics

### 7.1. Checking Exact Meter Names and Tags

After starting the application, run from PowerShell:

~~~powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics'

Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics/orders.accepted'

Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics/orders.processing?tag=outcome:success'

Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/metrics/spring.integration.send?tag=type:channel&tag=name:orders.input&tag=result:success'
~~~

In this lesson's direct Micrometer setup, `spring.integration.send` uses `type` to distinguish channel/handler; `name` identifies the component; `result` indicates success/failure; and `exception` describes the exception type. `QueueChannel` also exposes gauges `spring.integration.channel.queue.size` and `spring.integration.channel.queue.remaining.capacity`. These meters are not business order counters. See [Spring Integration Metrics and Management](https://docs.spring.io/spring-integration/reference/6.5/metrics.html).

Try filtering failures on the input channel:

~~~text
GET /actuator/metrics/spring.integration.send?tag=type:channel&tag=name:orders.input&tag=result:failure
~~~

With the synchronous flow and three sample requests, the count at `orders.input` is expected to be two successes and one failure. Avoid filtering by exception name upfront: the framework may wrap the business exception in a messaging exception. Inspect `availableTags` in the response to pick actual values.

Meters may not appear before corresponding activity occurs. When a query yields nothing, check the meter list and tags before concluding the application is uninstrumented.

### 7.2. Do Not Sum Timers Across All Components

With `DirectChannel`, `send()` invokes the consumer on the same call stack. Therefore, the send duration on `orders.input` can include the transformer, processor, and putting the result into the queue.

These timers measure nested intervals. Summing the input channel timer with the handler timer double-counts time. To evaluate properly:

- Use the timer at the synchronous entry point to observe cost from send until the entire synchronous segment returns.
- Use `orders.processing` to isolate processor duration.
- Use queue gauges to spot unconsumed results.
- When adding an asynchronous boundary, design an end-to-end measurement from intake to completion if end-to-end latency is needed.

For an intermediate queue, enqueue time does not represent how long a message waits in the queue. Likewise, a successful enqueue does not confirm downstream business processing succeeded.

### 7.3. Reading Prometheus Output

~~~powershell
(Invoke-WebRequest -Uri 'http://127.0.0.1:8080/actuator/prometheus').Content
~~~

Micrometer transforms names per backend conventions; for instance, counters and timers may appear as `orders_accepted_total`, `orders_failed_total`, and `orders_processing_seconds_count`. Always verify exact names in the scrape output before writing queries. Naming and tag conversion rules are described in [Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Example PromQL for the sample configuration:

~~~promql
sum(rate(orders_accepted_total{
  application="integration-observability-lab"
}[5m]))
~~~

Failure ratio across processor invocations:

~~~promql
sum(rate(orders_failed_total{
  application="integration-observability-lab"
}[5m]))
/
clamp_min(
  sum(rate(orders_failed_total{
    application="integration-observability-lab"
  }[5m]))
  +
  sum(rate(orders_accepted_total{
    application="integration-observability-lab"
  }[5m])),
  1e-9
)
~~~

p95 latency of successful processor invocations, when histograms are exported:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(orders_processing_seconds_bucket{
      application="integration-observability-lab",
      outcome="success"
    }[5m])
  )
)
~~~

These queries require Prometheus to scrape the application and have data within the observation window. The demo sending three requests on startup is only enough to explore meters; to observe meaningful `rate` and percentiles, generate steady load over multiple scrape intervals. Never use three requests to draw conclusions about service performance or reliability.

## 8. Interpreting Message History

### 8.1. Checking the Path Rather Than Hardcoding the Entire List

For a successful result, history must contain the channels in order:

~~~text
orders.input
  -> ...
  -> orders.normalized
  -> ...
  -> orders.completed
~~~

The `...` represents gateway or handler entries matching the tracking pattern. Exact names and entry counts depend on the actual components; `HistorySupport.names()` shows the list your application produces.

For an error in `orders.process`, the failed message is expected to have passed through `orders.input` and `orders.normalized`, and not `orders.completed`. An entry only proves the message was recorded at that point; it does not prove a business step committed successfully.

### 8.2. Timestamps in History Do Not Replace Timers

A history entry records the timestamp when a message is tracked at a component. The delta between two timestamps can include processing, scheduling, and queue wait time. It does not by itself provide full start/end times for each handler.

Use timestamps to reconstruct the sequence of events; use timers with well-defined measurement boundaries to evaluate latency. When comparing timestamps across machines, also account for clock synchronization.

### 8.3. Preserving Context When Transforming Messages

A transformer returning a payload as in the example lets the framework manage the reply message. If you need to build a `Message<?>` manually in a step, consider copying headers:

~~~java
Message<?> replacement = MessageBuilder
        .withPayload(newPayload)
        .copyHeaders(original.getHeaders())
        .build();
~~~

This snippet illustrates the case where `newPayload` and `original` are already available. Do not expect `id` or `timestamp` on the new message to match the old one. The `requestId` header is this lesson's explicit correlation key, independent of each message's ID.

A plain `copyHeaders` also does not fully handle cloning messages manually for parallel branches. Since Spring Integration 6.3, history is appended incrementally; the framework handles copying history at branching points it manages. When creating parallel branches manually outside that mechanism, check `cloneMessageHistoryIfAny()` on Spring Integration builders to avoid branches mutating a shared history concurrently. Details are in [Message History 6.5](https://docs.spring.io/spring-integration/reference/6.5/message-history.html).

### 8.4. Choosing Collection Points

In this lesson, the consumer reads history after receiving from `orders.completed`; on errors, the caller reads it from the failed message. If the application moves to an asynchronous flow, context can be collected inside an error flow.

When receiving an `ErrorMessage`, its payload is the throwable. To inspect the path of the business message that failed, locate `MessagingException.getFailedMessage()` in the cause chain or the original message supplied by the error strategy. The history of the error message itself, if present, describes the error-handling path and can differ from the business message's history.

Message history in headers does not create a durable audit log automatically, does not automatically cross every transport protocol, and is not a distributed trace. When sending over HTTP, Kafka, or to external systems, design header mapping, data formats, and correlation/trace context propagation at that boundary.

## 9. Testing Observability

Tests must verify both business outcomes and observability signals simultaneously. Checking only that the application starts up is not enough to prove a message carries history or meters recorded activity.

The class below uses JUnit 5, AssertJ, and Spring Test from `spring-boot-starter-test`. It creates a minimal context with an in-memory registry; it does not start an HTTP server and does not run the demo application's `CommandLineRunner`.

File `OrdersFlowTest.java`:

~~~java
package example.integration.metrics;

import java.util.List;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;

@SpringJUnitConfig(classes = {
        OrdersFlowConfig.class,
        OrdersFlowTest.Meters.class
})
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OrdersFlowTest {

    @Configuration(proxyBeanMethods = false)
    static class Meters {

        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }
    }

    @Autowired
    OrdersGateway gateway;

    @Autowired
    SimpleMeterRegistry registry;

    @Autowired
    @Qualifier("orders.input")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.completed")
    QueueChannel completed;

    @Test
    void recordsSuccessfulOrderAndItsHistory() {
        gateway.submit(request("O-201", " book ", 2, "req-201"));

        Message<?> reply = this.completed.receive(1000);

        assertThat(reply).isNotNull();
        assertThat(reply.getPayload()).isEqualTo(
                new OrdersFlowConfig.OrderResult(
                        "O-201", "BOOK", 2, "ACCEPTED"));
        assertThat(reply.getHeaders().get("requestId"))
                .isEqualTo("req-201");
        assertThat(HistorySupport.names(reply))
                .containsSubsequence(
                        "orders.input",
                        "orders.normalized",
                        "orders.completed");

        assertThat(this.registry.get("orders.accepted")
                .counter().count()).isEqualTo(1.0);
        assertThat(this.registry.get("orders.failed")
                .counter().count()).isZero();
        assertThat(this.registry.get("orders.processing")
                .tag("outcome", "success")
                .timer().count()).isEqualTo(1L);

        Timer sent = this.registry.find("spring.integration.send")
                .tags("type", "channel",
                        "name", "orders.input",
                        "result", "success")
                .timer();

        assertThat(sent).isNotNull();
        assertThat(sent.count()).isEqualTo(1L);
    }

    @Test
    void recordsFailureWithoutProducingACompletedOrder() {
        Throwable failure = catchThrowable(() ->
                this.input.send(
                        request("O-202", " fail ", 1, "req-202")));

        assertThat(failure).isInstanceOf(MessagingException.class);

        Message<?> failed = HistorySupport.failedMessage(failure);
        assertThat(failed).isNotNull();
        assertThat(failed.getHeaders().get("requestId"))
                .isEqualTo("req-202");

        List<String> path = HistorySupport.names(failed);
        assertThat(path)
                .containsSubsequence("orders.input", "orders.normalized")
                .doesNotContain("orders.completed");

        assertThat(this.completed.receive(0)).isNull();
        assertThat(this.registry.get("orders.accepted")
                .counter().count()).isZero();
        assertThat(this.registry.get("orders.failed")
                .counter().count()).isEqualTo(1.0);
        assertThat(this.registry.get("orders.processing")
                .tag("outcome", "failure")
                .timer().count()).isEqualTo(1L);

        Timer sent = this.registry.find("spring.integration.send")
                .tags("type", "channel",
                        "name", "orders.input",
                        "result", "failure")
                .timer();

        assertThat(sent).isNotNull();
        assertThat(sent.count()).isEqualTo(1L);
    }

    private static Message<OrdersFlowConfig.OrderRequest> request(
            String orderId, String sku, int quantity, String requestId) {

        return MessageBuilder.withPayload(
                        new OrdersFlowConfig.OrderRequest(
                                orderId, sku, quantity))
                .setHeader("requestId", requestId)
                .build();
    }
}
~~~

Each test receives a fresh context so counters from earlier tests do not affect later ones. Assertions rely on the relative order of explicit channels rather than tying the whole history to auto-generated handler names.

Do not use `Thread.sleep()` to wait in this synchronous flow. `receive(1000)` is a wait bound when checking output, not a performance measurement. If converting the flow to asynchronous execution, use bounded conditional waits for results and meters because completion time no longer coincides with when the sender finishes sending.

## 10. Switching to Micrometer Observation

Spring Integration 6.x supports Observation. You can replace the management annotation in the configuration above with:

~~~java
@EnableIntegrationManagement(
        observationPatterns = {"ordersGateway", "orders.*"})
~~~

You must also provide an `ObservationRegistry` and appropriate handlers. For metrics via Observation, collection is performed by an `ObservationHandler`; creating a registry alone is not enough for tracing or exporting data to a backend.

When switching mechanisms, check meter names and tags. For example, Observation meters include `spring.integration.producer`, `spring.integration.handler`, and `spring.integration.gateway`; standard tags use the `spring.integration.` prefix. Assertions looking for `spring.integration.send` with `type/name/result` in this lesson must be updated for components switched to Observation. See [Micrometer Observation in Spring Integration](https://docs.spring.io/spring-integration/reference/6.5/metrics.html#micrometer-observation).

For a minimal test context, an additional configuration connecting Observation to metrics could be:

~~~java
@Bean
ObservationRegistry observationRegistry(MeterRegistry meterRegistry) {
    ObservationRegistry registry = ObservationRegistry.create();
    registry.observationConfig().observationHandler(
            new DefaultMeterObservationHandler(meterRegistry));
    return registry;
}
~~~

Imports for the additional snippet:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
~~~

This is the approach when constructing a context manually; do not add another registry to a Boot application that already auto-configured Observation without checking existing beans. The handler in the example creates metrics from Observation; tracing additionally requires tracing handlers and bridges.

After switching, test again with one success message and one error message, inspect `availableTags`, and update assertions and dashboards to match observed meters. Do not sum numbers from multiple mechanisms to compute total requests without verifying whether they measure the same or different scopes.

## 11. Controlling Observability Data Volume

### 11.1. Keeping Tag Cardinality Bounded

Suitable tags might be:

| Tag | Sample value set |
| --- | --- |
| `outcome` | `success`, `failure` |
| `flow` | `orders`, `payments` |
| `route` | `standard`, `priority` |

`orderId`, `requestId`, emails, exception messages, and user-entered SKUs can generate unbounded values. Put them in log context or traces when searching for a specific request; keep metric tags to designed finite sets.

For example, 8 flows × 12 components × 2 outcomes produce at most 192 combinations across those dimensions. Adding a tag with 100,000 request IDs explodes the combination space; histograms multiply series further per combination. Account for tag count, value sets, buckets, and instance count when estimating cost.

### 11.2. Tracking History at Useful Points

The `orders.*` pattern fits the lab. For long flows or many loops, select points with diagnostic value such as ingress, post-normalization, pre-external integration, and egress.

When logging, prioritize `requestId`, error type, and the component list. Full payloads/headers may contain data unnecessary for investigation. Here, reading a list of names suffices to tell whether a message stopped before or after the processor.

A message's history can grow across retries or loops. If taking a snapshot to persist beyond processing lifetime, copy the needed values after the branch completes; never hold onto and arbitrarily mutate the history header of an in-flight message.

## 12. Extension Exercises

### 12.1. Error Before the Processor

Send an `OrderRequest` with `sku = null` so the transformer fails when calling `strip()`.

Before running, predict:

- The meter at `orders.input` records a failure.
- `orders.failed` remains 0 if the context has not processed any other requests.
- No results appear in `orders.completed`.
- History at the failure point has not reached `orders.normalized`.

This exercise checks your understanding of counter scope and identifies the first component absent from the expected path.

### 12.2. Adding a Router and Filter

Add a router for a bounded set of business groups, such as `standard` and `priority`, along with a filter having a dedicated discard channel for invalid requests.

Design observability criteria before writing the DSL:

1. Each branch has a stable channel name recognizable in history.
2. Dropped messages have a dedicated counter on the discard flow.
3. Explicitly define whether a filter dropping a message normally counts as a technical error under your configuration.
4. Test one message per branch and one dropped message.

Do not rely on exception counts alone to infer total rejected requests: a filter can drop a message without throwing an exception.

### 12.3. Inserting a QueueChannel Before the Processor

Replace the intermediate channel with a `QueueChannel` and configure a poller on the consuming endpoint. Then send a small, bounded burst of load.

Observe separately:

- Queue intake rate.
- Queue depth and consumption throughput.
- Processor completion count.
- How errors reach the error flow across the asynchronous boundary.
- Queue wait time vs. processor execution time.

Re-evaluate the meaning of the ingress timer: it no longer encompasses processing on the consumer thread as in the original `DirectChannel` setup.

### 12.4. Observing Retries and Aggregators

If adding retry, distinguish business request count from attempt count. One request can cause multiple processor invocations; name meters and assertions so attempt count is not mistaken for request count.

If adding an aggregator, track open waiting groups, completed groups, and expired groups. An aggregated output message does not automatically retain the full history of every member message in the group; to audit individual elements, design corresponding context retention.

## 13. Common Symptoms During Investigation

| Symptom | Check next |
| --- | --- |
| Missing `spring.integration.send` | Was a message sent; right registry; did components switch to Observation; is a meter filter blocking it |
| Meter exists yet HTTP endpoint unreachable | Web runtime, bind address/port, exposure settings, and access permissions |
| Meter found yet tag missing | Check `availableTags` and verify actual component name values |
| Missing `history` | History annotation, name pattern, managed components, and which step manually constructs new messages |
| Accepted counter increments yet queue has no results | Did consumer already read it; did output send fail; where does counter scope end |
| Processor counter stays flat despite input failures | Did messages fail before reaching the processor |
| Queue grows steadily while send succeeds | Downstream consumer, poller, executor, and processing speed |
| Summing timers yields more than wall-clock time | Are timers nested inside the same call stack |
| Error flow misses synchronous errors | Is caller receiving exceptions directly or is error routing explicitly configured |
| Prometheus shows no useful rate/p95 | Scrape count, traffic in window, and actual histogram buckets |

## 14. Lab Completion Criteria

The practice exercise is satisfactory when you reproduce all of the following evidence:

- Two successful messages carry normalized payloads, preserve `requestId`, and show history passing through input, intermediate, and output channels in order.
- An error in the processor increments the failure counter, produces no success result, and allows tracing the failed message.
- You can pick the right meter/tag to inspect channel activity without confusing it with business order counts.
- You can explain why a synchronous channel timer can encompass the handler, and why a successful enqueue does not prove downstream business work succeeded.
- Success and failure tests run independently without relying on accumulated counters from other tests or arbitrary sleep durations.
- If Observation is enabled, new meters/tags are identified and checks are updated accordingly.

When investigating an anomaly, start with metrics to narrow down scope and time, use `requestId` to locate related messages, and then cross-check history alongside the failure at the processing point. Combining these signals lets you verify flow paths and behavior with concrete data.