# Composing Functions with the | Operator and Declaring Multiple Functions with ;

Spring Cloud Stream allows applications to declare function beans following the Supplier, Function, and Consumer models. When an application has multiple processing steps, you can compose Functions into a pipeline using the | operator. When you need to activate multiple independent functions in the same application, you list the function names separated by ; in the spring.cloud.function.definition property.

These two declaration approaches solve different needs. Function composition forms a logical processing chain: the output of the preceding function becomes the input of the next function. Listing with a semicolon registers multiple separate functions; each function can have its own binding, destination, and consumer group. Understanding this difference clearly helps avoid creating unnecessary topics or accidentally turning independent tasks into a processing chain.

## 1. From function beans to function definitions

Spring Cloud Function recognizes beans of type Supplier<T>, Function<T, R>, or Consumer<T>. Spring Cloud Stream uses these beans as entry and exit points for message flows:

- Supplier produces data and has an output.
- Function receives data, transforms it, and returns a result.
- Consumer receives data and terminates the processing flow, with no output.

Example of a standalone Function:

~~~java
import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

When there is only one matching function bean, the framework can auto-discover it. When an application has multiple function beans, you should explicitly declare which function needs to be activated using:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
~~~

The definition property is a list of function bean names or function composition expressions. Spring Cloud Stream relies on this definition to create the corresponding bindings. The bean name must match the name in the configuration; method names are case-sensitive.

## 2. Composing Functions with the | operator

The | operator represents function composition from left to right. With the definition parseOrder|validateOrder|createEvent, data passes through parseOrder first, the result is passed to validateOrder, and then the result of the validation step is fed into createEvent.

~~~mermaid
flowchart LR
    I["Input binding"] --> A["parseOrder"]
    A -->|"OrderDraft"| B["validateOrder"]
    B -->|"ValidatedOrder"| C["createEvent"]
    C --> O["Output binding"]
~~~

Intermediate functions are invoked within the same application pipeline. Spring Cloud Stream only needs bindings at the input of the composed function and the output of the composed function. Each | does not automatically create an intermediate topic or queue.

### 2.1. Data type compatibility condition

The output type of one step must be compatible with the input type of the next step. If the first function has type Function<A, B>, the second function must accept B or a type to which B can be converted.

Example:

~~~java
public record OrderDraft(String orderId, String customerId, int quantity) {}

public record ValidatedOrder(
    String orderId,
    String customerId,
    int quantity
) {}

public record OrderAccepted(
    String orderId,
    String customerId,
    int quantity,
    String status
) {}
~~~

Declaring the three processing steps:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderPipeline {

    @Bean
    Function<String, OrderDraft> parseOrder() {
        return raw -> {
            String[] fields = raw.split(",");
            return new OrderDraft(
                fields[0].trim(),
                fields[1].trim(),
                Integer.parseInt(fields[2].trim())
            );
        };
    }

    @Bean
    Function<OrderDraft, ValidatedOrder> validateOrder() {
        return order -> {
            if (order.orderId().isBlank()
                    || order.customerId().isBlank()
                    || order.quantity() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            return new ValidatedOrder(
                order.orderId(),
                order.customerId(),
                order.quantity()
            );
        };
    }

    @Bean
    Function<ValidatedOrder, OrderAccepted> createEvent() {
        return order -> new OrderAccepted(
            order.orderId(),
            order.customerId(),
            order.quantity(),
            "ACCEPTED"
        );
    }
}
~~~

The three types link together:

| Step | Input type | Output type |
|---|---|---|
| parseOrder | String | OrderDraft |
| validateOrder | OrderDraft | ValidatedOrder |
| createEvent | ValidatedOrder | OrderAccepted |

Defining the pipeline:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent"
~~~

The order in the chain matters. If changed to validateOrder|parseOrder|createEvent, the input and output types no longer match the declared contract. Design intermediate data types before composing functions so that compatibility errors are caught early.

### 2.2. Bindings of a composed function

Suppose the definition is parseOrder|validateOrder|createEvent; the pipeline receives data from one input binding and emits the final result through one output binding. The binding names are derived from the composed function definition:

- parseOrder|validateOrder|createEvent-in-0
- parseOrder|validateOrder|createEvent-out-0

Configuration example:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent"
    stream:
      bindings:
        "parseOrder|validateOrder|createEvent-in-0":
          destination: orders.raw
          group: order-pipeline
          content-type: text/plain
        "parseOrder|validateOrder|createEvent-out-0":
          destination: orders.accepted
          content-type: application/json
~~~

The binding name contains the | character, so it should be enclosed in double quotes in YAML to clearly indicate it is a single configuration key. The destination orders.raw is where initial data is received; orders.accepted receives the result after the entire pipeline.

If you want to use shorter binding names, you can map the implicit binding names via spring.cloud.stream.function.bindings, and then configure destinations using the alias names. Mapping does not change the function composition order; it only renames the logical port used in binding configuration.

### 2.3. Defining pipeline boundaries

When composing functions, clearly identify which point receives messages from outside and which point returns results externally. For a chain consisting only of Functions, the first function provides the input and the last function provides the output. If the design includes a Supplier as the source or a Consumer as the final step, the overall signature changes accordingly: a Supplier requires no input binding, and a Consumer produces no output binding.

An imperative Supplier requires a poller mechanism to generate data on a schedule; a Consumer ends processing without emitting an output. These components still follow the data type rules between steps. When combining multiple function types in a single definition, check the startup logs to confirm that the function is created with the expected boundary bindings.

## 3. Declaring multiple independent functions with ;

The ; character separates independent function definitions. It does not connect the output of the preceding function to the input of the next function. Example:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder;publishMetrics"
~~~

The framework activates two separate beans:

- validateOrder receives and processes the order stream.
- publishMetrics receives and processes the metrics stream.

Each function has its own bindings. If both are Functions, each has its own input and output bindings:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder;publishMetrics"
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.submitted
          group: order-validation
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
        publishMetrics-in-0:
          destination: metrics.events
          group: metrics-publisher
          content-type: application/json
        publishMetrics-out-0:
          destination: metrics.published
          content-type: application/json
~~~

Flow diagram:

~~~mermaid
flowchart LR
    A[("orders.submitted")] --> B["validateOrder"]
    B --> C[("orders.validated")]
    D[("metrics.events")] --> E["publishMetrics"]
    E --> F[("metrics.published")]
~~~

Two functions do not call each other simply because they are listed in the same property. They operate as two independent logical flows within the same application. If validateOrder emits to orders.validated and publishMetrics needs to process that result, configure the input destination of publishMetrics to point to the appropriate destination or design a pipeline composition if the two steps must run directly in sequence within the same processing invocation.

### 3.1. Multiple function types in the same definition

The list can include different function types. For example, a Function that processes orders and a Consumer that records notifications:

~~~java
@Bean
Function<OrderDraft, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(
        order.orderId(),
        order.customerId(),
        order.quantity(),
        "ACCEPTED"
    );
}

@Bean
Consumer<MetricSnapshot> recordMetric() {
    return snapshot -> metricsRepository.save(snapshot);
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: "acceptOrder;recordMetric"
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.validated
          group: order-acceptance
        acceptOrder-out-0:
          destination: orders.accepted
        recordMetric-in-0:
          destination: metrics.snapshots
          group: metrics-recorder
~~~

acceptOrder has both input and output bindings. recordMetric only has an input binding because a Consumer returns no result. Do not declare recordMetric-out-0 if the Consumer produces no output.

### 3.2. Combining composition and an independent list

A definition can contain multiple elements, where each element can be a composed pipeline. Example:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent;recordMetric"
~~~

Meaning:

1. parseOrder|validateOrder|createEvent is a three-step pipeline executed in order.
2. recordMetric is an independent function in the same application.

The | operator is resolved within a single function definition; ; separates definitions at the list level. Reading it this way helps avoid mistaking a long chain for independent functions or vice versa.

## 4. Distinguishing composition from connecting via a broker

Both composition and connecting via destinations can form a processing chain, but their operational mechanisms differ:

| Characteristic | Function composition (|) | Connecting services via broker |
|---|---|---|
| Boundary | Functions within the same pipeline of a single application | Bindings and services that can be deployed separately |
| Data transfer | Java values are passed from one function to the next | Messages are sent and received via the broker |
| Intermediate topic/queue | Not automatically created | Destinations exist at communication points |
| Independent deployability | Composition steps are packaged together in one application | Producer and consumer can be deployed independently |
| Failures between steps | Errors propagate within the same pipeline invocation | Can have retries, acknowledgments, and DLQ at message boundaries |

Choose composition when the steps form a single logical processing workflow that needs to change and deploy together. Choose broker-based communication when you need to decouple services, persist messages, allow multiple independent consumers, or scale individual parts separately.

Do not compose all steps into one long pipeline if the steps need to be deployed independently or have different retry policies. Conversely, there is no need to create a topic for every small transformation if they are simply pure steps within the same workflow.

## 5. Error handling in a pipeline

If a Function in the middle of a pipeline throws an exception, that pipeline execution fails and the exception propagates out to the integration layer. Subsequent steps do not proceed with an invalid result. Retry or error-handling mechanisms apply at the binding boundary and depend on the Spring Cloud Stream and binder configuration.

For example, if validateOrder rejects an order with an exception:

~~~java
@Bean
Function<OrderDraft, ValidatedOrder> validateOrder() {
    return order -> {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return new ValidatedOrder(
            order.orderId(),
            order.customerId(),
            order.quantity()
        );
    };
}
~~~

createEvent is not called for the failed message. If the input binding has retry configured, the framework may re-invoke the entire pipeline for that message. Therefore, steps that run before an error occurs should avoid side effects that cannot be safely repeated. If you need to write to a database or call an external service, design appropriate idempotency and transaction boundaries.

In composition, intermediate steps do not have their own bindings to configure independent retries. If a step requires its own delivery policy, timeout, or DLQ, consider splitting that step into an independent consumer/producer connected via the broker.

## 6. Verifying function definitions and bindings at startup

When there are multiple function beans, a common mistake is missing a name or using incorrect syntax in spring.cloud.function.definition.

| Configuration | Meaning |
|---|---|
| normalizeOrder | Activates one function |
| parseOrder|validateOrder | Composes two functions in order |
| validateOrder;publishMetrics | Activates two independent functions |
| parseOrder|validateOrder;publishMetrics | One composed pipeline and one independent function |

Errors to check for:

- Names in definition do not match bean names.
- A bean is not registered due to missing configuration or component scan.
- The output type of the preceding function is incompatible with the input type of the next function.
- Using ; when intending to compose functions, or using | when intending independent activation.
- Configuring bindings using a single bean name when a composition name is actually used.
- Declaring an output binding for a Consumer or omitting the input binding of a Function.

Set logging at an appropriate level for Spring Cloud Function and Spring Cloud Stream to see which functions are selected, which bindings are created, and which binder is used. In production, do not leave broad DEBUG logging enabled for extended periods because logs can grow rapidly and contain operational metadata.

## 7. Testing composition and multiple functions

You should test each Function directly first, then verify how they are composed and connected to bindings.

### 7.1. Unit testing individual steps

Example of testing validateOrder:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ValidateOrderTest {

    @Test
    void keepsValidOrderData() {
        var function = new OrderPipeline().validateOrder();
        var result = function.apply(
            new OrderDraft("order-501", "customer-8", 2)
        );

        assertEquals("order-501", result.orderId());
        assertEquals("customer-8", result.customerId());
        assertEquals(2, result.quantity());
    }
}
~~~

Unit tests verify the rules of each step without needing to start a broker.

### 7.2. Test Binder for pipelines

Spring Cloud Stream Test Binder lets you test input and output bindings in an application without needing a real broker. With composition, send a payload to the pipeline's input binding and verify the final result at the output binding.

Test scenarios should verify:

1. The input payload is converted to the type expected by the first function.
2. Steps execute in the right order and pass the right data types.
3. The final output is emitted to the correct binding.
4. Error cases in an intermediate step do not produce valid output.
5. With multiple independent definitions, a message sent to one function's binding is not mistakenly processed by another function.

Test Binder does not fully simulate partitioning, consumer groups, rebalancing, or broker-specific acknowledgments. Use integration tests with Kafka, RabbitMQ, or Pulsar when you need to verify those characteristics.

## 8. Syntax selection workflow

Before declaring spring.cloud.function.definition, determine the relationship between steps:

1. If the result of step A must become the direct input of step B in the same workflow, use A|B.
2. If A and B process two separate streams, use A;B.
3. If there are multiple sequential steps and one independent task, use A|B|C;D.
4. Check data types between each pair of functions in the pipeline.
5. Identify the input/output bindings at the boundaries of each definition.
6. Set the destination and group for each binding according to consumption requirements.
7. Test individual functions, the pipeline, and independent bindings.
8. Check startup logs to confirm that the function definitions and bindings were created as expected.

A combined example:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|createEvent;recordMetric"
    stream:
      bindings:
        "parseOrder|validateOrder|createEvent-in-0":
          destination: orders.raw
          group: order-pipeline
        "parseOrder|validateOrder|createEvent-out-0":
          destination: orders.accepted
        recordMetric-in-0:
          destination: metrics.snapshots
          group: metrics-recorder
~~~

The order pipeline receives raw data, validates it, and creates an accepted event. The recordMetric function reads an independent metrics stream. Each stream has its own destination and group, while the steps inside the pipeline share a single logical execution.

## 9. Key takeaways

- | composes functions in order from left to right.
- The output type of the previous step must be compatible with the input type of the next step.
- A composed pipeline has bindings at its boundaries; intermediate steps do not automatically create destinations.
- ; separates multiple independent function definitions.
- Each independent function can have its own input/output bindings depending on whether it is a Supplier, Function, or Consumer.
- Composition does not replace a broker when you need service decoupling or independent delivery policies.
- An error in one step can fail the entire pipeline invocation; design external side effects to be idempotent.

## Official References

- [Spring Cloud Function - Function Composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): functional programming model and how to compose functions.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html): function definitions, bindings, and broker integration.
- [Spring Cloud Stream - Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): how functional beans are connected to input and output bindings.
