# Micrometer tags

In the **Metrics and observability** chapter of the **SPRING_INTEGRATION_CORE** module, tags help slice message flow activity along dimensions such as component, sender source, and processing outcome. This lesson focuses on choosing and using tags when observing Messages, MessageChannels, endpoints, and Java DSL flows.

A single application-wide error total does not tell you whether errors happened during order validation or when calling the payment system. Tags add context to answer that question. They also determine how many meters and time series are created, making tag design part of integration flow design.

## 1. Objectives and scope

After this lesson, you will be able to:

- Distinguish metric names, tag keys, tag values, and measured values.
- Read tags provided by Spring Integration and recognize differences when using Observation.
- Design a bounded set of tags for a message processing flow.
- Normalize data from message headers before using it as a tag.
- Apply common tags and registration limits using MeterFilter.
- Interpret measurement results according to exact channel, handler, and business boundaries.

The main examples use Java 17 or higher, Spring Integration 6.x, and Micrometer managed by the project's appropriate BOM. The examples configure plain Spring to show clearly where the registry is created, without depending on Spring Boot auto-configuration. The Observation snippets later are a separate extension.

## 2. What are tags and how do they identify a meter?

A tag is a key–value pair describing a classification dimension of a measurement:

```text
Meter name: orders.validation

Tags:
  flow=orders
  stage=validate
  source=web
  outcome=success

One measurement:
  processing duration = 12 ms
```

Here:

- `orders.validation` states which operation is being measured.
- `source=web` identifies the message group.
- `outcome=success` identifies the outcome.
- `12 ms` is the observed value, not a tag.

Within a registry, **the name and tag set together identify a meter**. Combinations `source=web` and `source=mobile` are two different meters despite sharing a name. Registering again with the same name, same tags, and same meter type typically returns the existing meter. Do not reuse the same identifier for measurements with different semantics. The foundations of this model are described in [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

Example:

```java
registry.counter("orders.rejected", "reason", "invalid").increment();
registry.counter("orders.rejected", "reason", "duplicate").increment();
registry.counter("orders.rejected", "reason", "invalid").increment();
```

The three calls above create two counters by reason, with values 2 and 1 respectively. Embedding the reason into the name like `orders.rejected.invalid` loses a convenient classification dimension; dashboards would have to query multiple names instead of filtering one tag.

Keep names and tag keys in lowercase dot-separated convention when needed. Registries may convert them to backend conventions; for instance, a dot-separated name can appear with underscores in Prometheus data. See [Micrometer — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

### Distinguishing tags from message headers

Message headers belong to data flowing through the pipeline. Tags belong to observability data recorded into the registry. These two sets are not automatically identical.

```text
Headers:
  source = WEB
  orderId = ORD-1928
  correlationId = c-8139

Tags explicitly chosen by the application:
  source = web
  flow = orders
  stage = validate
```

Only normalized `source` is chosen for the metric. The `orderId` header can still serve business logic or log correlation without becoming a tag.

## 3. Reading Spring Integration's built-in tags

### 3.1. Direct metrics via MeterRegistry

In the direct metrics mechanism, Spring Integration provides the `spring.integration.send` timer for channels and handlers. These tags distinguish measurements:

| Tag key | Meaning | Example |
|---|---|---|
| `type` | Component type | `channel`, `handler` |
| `name` | Component name | `ordersInput` |
| `result` | Operation outcome | `success`, `failure` |
| `exception` | Exception class name or none | `none` |

The case `result=failure`, `exception=none` can occur when `send()` returns `false`. Official documentation presents this schema in [Spring Integration — Micrometer Integration](https://docs.spring.io/spring-integration/reference/6.5/metrics.html#micrometer-integration).

Key point to remember: the `name` tag is the component name, not the metric name. When searching in the registry, filter the meter name and tags separately:

```java
registry.find("spring.integration.send")
        .tags("type", "channel", "name", "ordersInput")
        .timers()
        .forEach(timer -> System.out.println(timer.getId()));
```

Endpoint names in Java DSL and actual handler names can differ. Giving endpoints clear names helps operations, yet you should still inspect actual `Meter.Id` values before hardcoding queries by `name`.

### 3.2. Metrics through Observation

Spring Integration also provides the Observation mechanism, with names such as `spring.integration.producer`, `spring.integration.handler`, and `spring.integration.gateway`. Tags in these conventions use keys like `spring.integration.name` and `spring.integration.type`; gateways also include `spring.integration.outcome`. Do not carry direct-mechanism queries using `name`, `type`, `result` verbatim over to the Observation schema. See [Spring Integration's Micrometer Observation section](https://docs.spring.io/spring-integration/reference/metrics.html#micrometer-observation).

When troubleshooting "metric not found", determine which mechanism is enabled before adding tags or changing dashboards.

## 4. Choosing tags based on operational questions

Suppose a flow receives orders from a website, mobile app, and partners. You want to know:

1. Which source is sending the most invalid orders?
2. Is the validation step slower than usual?
3. On which environment are technical errors rising?

You can propose a schema for the business timer `orders.validation` as follows:

| Tag key | Scope | Value set in example |
|---|---|---|
| `application` | Whole application | `order-integration` |
| `environment` | One deployment | `lab` |
| `flow` | Business flow | `orders` |
| `stage` | Measured step | `validate` |
| `source` | Per message after normalization | `web`, `mobile`, `partner`, `other`, `unknown` |
| `outcome` | Validation step outcome | `success`, `rejected`, `failure` |

This is an application-designed schema, not Spring Integration's default tag set.

Outcome conventions must be unambiguous:

- `success`: data is valid and validation finished normally.
- `rejected`: data failed business validation rules.
- `failure`: a technical error occurred while running validation.

An order rejected according to business rules does not necessarily have the same operational meaning as a database connection failure. Keeping the two separate enables appropriate alerting.

Do not use a common tag named `name` for the application name, because that key already has a specific meaning in Spring Integration's direct metrics. Using `application` avoids key collisions and makes queries clearer.

## 5. Cardinality: cost lies in the number of combinations

The cardinality of a tag is the number of distinct values it can take. Unbounded values such as request IDs, timestamps, or arbitrary text can make meter counts grow continuously. [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html) explains this risk to memory and observability backends.

With the example schema:

```text
flow:     1 value
stage:    1 value
source:   5 values
outcome:  3 values

Design combination bound:
1 × 1 × 5 × 3 = 15 meters for orders.validation in one registry
```

This is the upper bound of possible combinations; meters never used yet may not appear.

Suppose you expand to two flows, four stages, keeping five sources and three outcomes:

```text
2 × 4 × 5 × 3 = 120 combinations
```

If you further add `order.id` with 100,000 values, the dimensional product limit becomes:

```text
120 × 100,000 = 12,000,000 combinations
```

Not every system materializes the full product, but a dimension growing with business data breaks the finiteness of the schema. Hashing the order ID does not solve the problem: the number of distinct values stays nearly the same.

Also distinguish **number of meters** from **number of time series**. A Timer exports count and total duration; backends may also export max, histogram buckets, or other statistics. Thus 15 timers do not mean only 15 time series. When enabling histograms or scaling application replicas, account for the corresponding multiplier. Timer quantities are described in [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html).

## 6. Common tags and per-message tags

### Common tags

Use common tags for values fixed over the registry's lifecycle: application name, environment, or deployment region. Configure them before registering meters.

```java
registry.config().commonTags(
        "application", "order-integration",
        "environment", "lab");
```

### Per-message tags

Message source and processing outcome are determined at the measurement point. Input values must pass through a normalization function with a bounded output set:

```text
" WEB "       → web
"Mobile"      → mobile
"partner"     → partner
missing       → unknown
"campaign-17" → other
"campaign-18" → other
```

Do not call `commonTags("source", currentSource)` on each incoming message. Common tags are not a per-request mutable context holder.

Similarly, do not use `MeterFilter.map()` to read the current message from a ThreadLocal. Filters map identifiers at meter registration time; they are not interceptors called once per measurement. Per-request data must be handled at the instrumentation site. These configuration rules are stated in [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html).

## 7. Complete example with Java DSL

### 7.1. Flow and measurement boundary

The example uses:

```text
Message<String>
    │
    ▼
ordersInput: DirectChannel
    │
    ▼
endpoint validateOrder
    │
    ▼
OrderValidator.validate(...)
    └── Timer orders.validation
        tags: flow, stage, source, outcome
```

The payload is an illustrative order code string. Blank strings are rejected; the string `simulate-error` demonstrates a technical failure. This is synthetic data to observe tag behavior.

Required libraries on the classpath:

- `org.springframework.integration:spring-integration-core`.
- `io.micrometer:micrometer-core`.
- Compatible Spring Framework dependencies managed via your project's BOM.

`SimpleMeterRegistry` only stores numbers in memory for learning and testing. This example does not expose an HTTP endpoint or export data to Prometheus.

### 7.2. Demonstration code

Place the following components in a `MicrometerTagsLesson` class in your practice application:

```java
import java.util.Locale;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class MicrometerTagsLesson {

    @Bean
    public SimpleMeterRegistry meterRegistry() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        registry.config().commonTags(
                "application", "order-integration",
                "environment", "lab");

        registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "orders.validation",
                        "source",
                        5,
                        MeterFilter.deny()));

        return registry;
    }

    @Bean
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public OrderValidator orderValidator(MeterRegistry registry) {
        return new OrderValidator(registry);
    }

    @Bean
    public IntegrationFlow ordersFlow(OrderValidator validator) {
        return IntegrationFlow.from("ordersInput")
                .handle(validator, "validate",
                        endpoint -> endpoint.id("validateOrder"))
                .get();
    }

    public static final class OrderValidator {

        private final MeterRegistry registry;

        public OrderValidator(MeterRegistry registry) {
            this.registry = registry;
        }

        public void validate(Message<String> message) {
            String source = normalizeSource(
                    message.getHeaders().get("source"));

            Timer.Sample sample = Timer.start(this.registry);
            String outcome = "failure";

            try {
                String orderCode = message.getPayload();

                if (orderCode.isBlank()) {
                    outcome = "rejected";
                    throw new IllegalArgumentException(
                            "Order code must not be blank");
                }

                if ("simulate-error".equals(orderCode)) {
                    throw new IllegalStateException(
                            "Simulated technical failure");
                }

                // Data validation step completed.
                outcome = "success";
            }
            finally {
                Timer timer = this.registry.timer(
                        "orders.validation",
                        "flow", "orders",
                        "stage", "validate",
                        "source", source,
                        "outcome", outcome);

                sample.stop(timer);
            }
        }

        private static String normalizeSource(Object rawValue) {
            if (!(rawValue instanceof String text)) {
                return "unknown";
            }

            String value = text.strip().toLowerCase(Locale.ROOT);
            return switch (value) {
                case "web" -> "web";
                case "mobile" -> "mobile";
                case "partner" -> "partner";
                case "" -> "unknown";
                default -> "other";
            };
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             MicrometerTagsLesson.class)) {

            MessageChannel input =
                    context.getBean("ordersInput", MessageChannel.class);
            MeterRegistry registry =
                    context.getBean(MeterRegistry.class);

            send(input, "ORD-1", " WEB ", false);
            send(input, "", "mobile", true);
            send(input, "simulate-error", "partner", true);
            send(input, "ORD-2", null, false);

            for (int i = 0; i < 1_000; i++) {
                send(input, "ORD-" + (i + 3),
                        "untrusted-source-" + i, false);
            }

            registry.find("orders.validation").timers()
                    .forEach(timer -> System.out.printf(
                            "%s count=%d%n",
                            timer.getId().getTags(),
                            timer.count()));

            Timer otherSuccess = registry.get("orders.validation")
                    .tags("source", "other", "outcome", "success")
                    .timer();

            if (otherSuccess.count() != 1_000) {
                throw new AssertionError(
                        "Unexpected count for source=other");
            }

            if (registry.find("orders.validation").timers().size() > 15) {
                throw new AssertionError(
                        "Tag combinations exceeded the design limit");
            }
        }
    }

    private static void send(
            MessageChannel input,
            String payload,
            Object source,
            boolean expectFailure) {

        MessageBuilder<String> builder =
                MessageBuilder.withPayload(payload);

        if (source != null) {
            builder.setHeader("source", source);
        }

        try {
            if (!input.send(builder.build())) {
                throw new AssertionError("Message was not accepted");
            }
        }
        catch (MessagingException ex) {
            if (!expectFailure) {
                throw ex;
            }
            return;
        }

        if (expectFailure) {
            throw new AssertionError("Expected a handler failure");
        }
    }
}
```

### 7.3. Explaining the decisions in the example

**Normalize before registering a meter.** One thousand values of `untrusted-source-...` all map to `other`. No separate meter is created per input string.

**Keep tag keys consistent across every branch.** Success, rejection, and technical failure all carry `flow`, `stage`, `source`, and `outcome`. No branch omits `source` when the header is missing.

**Select outcome at completion.** Initializing `failure` ensures unexpected exceptions are not labeled as success. The blank-input branch explicitly sets `rejected`. The `finally` block guarantees both normal and exception paths stop the sample.

**Set an explicit timing boundary.** The business timer starts after header normalization and stops after validation. It does not measure wait time in an external queue outside this flow.

**Keep detailed data in the message.** Order code stays in the payload. The timer has no `order.id`, `message.id`, or error-message string tags.

**Use the same registry.** Business meters and integration components share the registry bean in the ApplicationContext. A standalone registry created inside a handler would isolate numbers from where metrics are configured and exported.

The example picks the meter when stopping the sample so the final outcome is placed into tags, following standard usage of [Timer.Sample](https://docs.micrometer.io/micrometer/reference/concepts/timers.html#_storing_start_state_in_timer_sample).

### 7.4. Expected results

In a fresh ApplicationContext, only observed combinations are created:

| source | outcome | count |
|---|---|---:|
| `web` | `success` | 1 |
| `mobile` | `rejected` | 1 |
| `partner` | `failure` | 1 |
| `unknown` | `success` | 1 |
| `other` | `success` | 1,000 |

Total validation runs equal 1,004; actual business timer count is 5. Each timer also carries the fixed tags `application`, `environment`, `flow`, `stage`. Tag print order is not an assertion requirement.

Handler exceptions propagate synchronously back through DirectChannel and may be wrapped by Spring Integration in MessagingException. The example's `send` helper only catches the two expected failures to continue the demo. In a real application, error-handling policy must align with your gateway, error channel, and synchronous or asynchronous model.

## 8. MeterFilter is a protective limit, not business normalization

In the example:

```java
MeterFilter.maximumAllowableTags(
        "orders.validation", "source", 5, MeterFilter.deny())
```

The filter caps distinct values of the `source` key on meters matching the name prefix. It does not cap total combinations across all keys and does not know which five values are valid.

If a handler records a thousand distinct source values directly, the first five may be kept while subsequent ones are denied registration. You both lose observability data and lack useful grouping. When using deny, a blocked meter records no measurements; business operations do not fail because of it. See [Meter Filters — Deny or Accept Meters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html#_deny_or_accept_meters).

Therefore, the example combines two layers:

1. `normalizeSource` defines the meaningful value set.
2. MeterFilter caps registration if another instrumentation site violates the design.

If you need to fix a schema already producing too many values, prefer fixing where tags are created. Dropping a dimension with a filter can collapse multiple meters into the same identifier; dashboards lose the ability to slice by that dimension. You also cannot recover collapsed detail solely by changing queries.

## 9. Observation: distinguishing low cardinality and high cardinality

Micrometer Observation classifies metadata into two groups:

| Group | Suitable purpose | Example |
|---|---|---|
| Low cardinality | Grouping metrics with a bounded set of values | `flow=orders`, `source=web` |
| High cardinality | Correlating one specific execution | `order.id=ORD-1928` |

Marking a value as low cardinality does not reduce its actual distinct values. Attaching distinct order IDs to a low-cardinality key still causes cardinality explosion. Concepts and APIs are described in [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).

With standard Observation meter handlers, only low-cardinality key-values become meter tags. High-cardinality metadata can feed tracing when an appropriate handler and exporter exist; creating an ObservationRegistry alone does not enable tracing. See [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) on distinguishing the two metadata types.

### 9.1. Enabling Observation for Spring Integration components

In a plain Spring configuration sharing an existing MeterRegistry, you can add the following configuration:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegrationManagement;

@Configuration
@EnableIntegrationManagement(observationPatterns = "*")
public class IntegrationObservationConfig {

    @Bean
    public ObservationRegistry observationRegistry(MeterRegistry registry) {
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(registry));
        return observations;
    }
}
```

This configuration must be registered in the ApplicationContext alongside the flow configuration. In a plain Spring example, pass both configuration classes to the AnnotationConfigApplicationContext constructor.

`observationPatterns = "*"` selects all eligible components to attach the ObservationRegistry. By default this attribute does not select everything; see [EnableIntegrationManagement — observationPatterns](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/config/EnableIntegrationManagement.html#observationPatterns()).

If a Spring Boot application already provides an ObservationRegistry and meter handler, use the existing setup to avoid duplicate registration. The snippet above illustrates an application managing registries itself.

`DefaultMeterObservationHandler` creates timers from the Observation lifecycle and uses low-cardinality key-values. Timers tracking active tasks may only see tags present at start time, so tags known only at completion do not necessarily appear on `.active` meters. See [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).

### 9.2. Metadata for a business Observation

The snippet below illustrates a custom business method receiving an ObservationRegistry and a valid order ID:

```java
void inspectOrder(ObservationRegistry observations, String orderId) {
    Observation.createNotStarted("orders.inspection", observations)
            .lowCardinalityKeyValue("flow", "orders")
            .lowCardinalityKeyValue("source", "web")
            .highCardinalityKeyValue("order.id", orderId)
            .observe(() -> {
                // Perform the business logic to observe.
            });
}
```

This snippet requires importing `io.micrometer.observation.Observation`. It creates a new business observation; it does not automatically add tags to internal Spring Integration observations.

If you want to customize tags on framework-created observations, use a convention suited to that component type and context. Keep required standard keys and only add dimensions with bounded value sets. Do not use MeterFilter as a tool to read message context.

## 10. Reading results and building accurate queries

### 10.1. Inspecting directly in the registry

After sending data, list the actual identifiers:

```java
registry.find("orders.validation").timers()
        .forEach(timer -> {
            System.out.println(timer.getId().getName());
            System.out.println(timer.getId().getTags());
            System.out.println(timer.count());
        });
```

A timer already has a count, so do not add a counter just to count the exact same events the timer measures. Use a separate counter when measuring a different event, such as messages dropped by a filter before reaching validation.

When testing tagged metrics, do not only verify "this name exists". Verify tag keys, normalized values, and counts per group.

### 10.2. Exporting to Prometheus

To export data, you need a Prometheus registry and a scrape endpoint; SimpleMeterRegistry does not provide that. Furthermore, PrometheusMeterRegistry requires keeping the same set of tag keys across meters sharing a name. Use `unknown` when source is missing instead of omitting the `source` key. Integration details are presented in [Micrometer — Prometheus](https://docs.micrometer.io/micrometer/reference/implementations/prometheus.html).

If the actual export of the timer produces the series `orders_validation_seconds_count`, you can compute traffic by source:

```promql
sum by (source) (
  rate(orders_validation_seconds_count{
    application="order-integration",
    environment="lab",
    flow="orders",
    stage="validate"
  }[5m])
)
```

Technical error ratio across all completed validations in the same scope:

```promql
sum(
  rate(orders_validation_seconds_count{
    application="order-integration",
    environment="lab",
    flow="orders",
    stage="validate",
    outcome="failure"
  }[5m])
)
/
sum(
  rate(orders_validation_seconds_count{
    application="order-integration",
    environment="lab",
    flow="orders",
    stage="validate"
  }[5m])
)
```

Both queries are examples based on the designed schema. Verify series names from actual scrape output before using them, as naming conventions and registry settings may differ. When there is no traffic, the denominator is zero or the series does not exist yet; dashboards and alerts must represent that state appropriately for operations.

The `rejected` ratio can be calculated separately to monitor input data quality. Do not add `rejected` into technical failures if your alert definition only cares about infrastructure or execution failures.

## 11. Aligning tags with EIP boundaries

The same message can pass through multiple components. Measurement meaning depends on start and end points.

| Integration component or pattern | Candidate classification dimension | What must be defined |
|---|---|---|
| Transformer | `stage=normalize`, bounded `outcome` | Measuring each transformation or the whole flow? |
| Router | `route=standard/priority/other` | Are branch names fixed or taken straight from input data? |
| Filter | `decision=accepted/rejected` | Do discarded messages reach downstream timers? |
| Aggregator | `release.reason=size/timeout/other` | Counting incoming messages or released groups? |
| Gateway | `operation=submit/cancel` | Ends on reply or as soon as message is sent? |
| Retry | `outcome` or `attempt.bucket=first/retried` | Measuring each attempt or the final outcome of an operation? |

The dimensions in the table are business suggestions chosen by the designer, not automatic tags guaranteed by the framework.

With DirectChannel, send time can include synchronous handler execution time. With asynchronous handoff channels, send measurements usually do not cover all downstream processing. Therefore, do not label every send timer "end-to-end latency".

Also do not add channel counts and handler counts and call the sum "order count". One execution can be observed at both points. If you want completed order counts, place a business metric at the exact completion point, while clearly defining counting policy for retries or message redeliveries.

## 12. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using every header as a tag | Combinations grow with input data | Select necessary keys and normalize against an allowed list |
| Putting orderId in the meter name | Creates unbounded metric names | Use one stable name; correlate orders via logs or traces |
| Using exception message as a tag | Every error text can become a new value | Use bounded error categories or class names when appropriate |
| Adding a tag only on the success branch | Inconsistent schema | Keep the same key set and use a defined fallback value |
| Registering common tags after meters exist | Meters may be inconsistent | Configure the registry before instrumentation runs |
| Setting outcome=success before processing | Exceptions may be mislabeled | Select outcome when the operation finishes |
| Relying on tag limits without normalization | Part of measurements gets dropped | Normalize at the source first, then apply limits |
| Believing lowCardinalityKeyValue bounds values itself | Identifiers still inflate meter counts | Design and enforce a finite value set yourself |
| Switching from direct metrics to Observation with unchanged queries | Dashboards miss names or keys | Inspect the actual schema of the running mechanism |
| Using an intermediate step's timer as order completion count | Misses later steps or miscounts retries | Place metrics at the business boundary to measure |

## 13. Self-practice exercises

1. Extend the normalization function to treat `" APP "` as an alias for `mobile`. Predict whether timer count increases, then verify via the Meter.Id list.
2. Send 10,000 messages with distinct source headers and valid payloads. Counts should rise in the `other` group while the number of `source` values remains bounded.
3. Add a `duplicate` outcome to the business schema. Update definitions, placement of the outcome, and combination-limit math before adding instrumentation.
4. Replace DirectChannel with an asynchronous channel in your practice application. Identify which timer measures handoff, which measures validation, and how to wait for completion before reading metrics.
5. Add a filter before the validator. Explain why total sent messages can exceed the `orders.validation` count, then pick a suitable measurement point for discarded messages.

Success criteria: being able to explain the meaning of each tag, determine the output value set, and link counts to the exact measured event. A well-designed tag schema answers concrete operational questions while keeping meter counts within expected bounds.