# Selecting Active Functions with spring.cloud.function.definition

In a Spring Cloud Stream application, a project may declare multiple function beans to handle different event streams. The `spring.cloud.function.definition` property tells Spring Cloud Function which beans should be activated and brought into Spring Cloud Stream's binding model.

This property selects functions by bean name. It does not create beans, decide the broker, or name topics, exchanges, or queues. After selecting functions, you still configure the corresponding input/output bindings under `spring.cloud.stream.bindings`.

## 1. Why Function Selection Is Needed

Spring Cloud Stream supports three primary function types:

| Bean Type | Role | Default Binding |
|---|---|---|
| `Supplier<T>` | Produces and publishes data | `<beanName>-out-0` |
| `Function<T, R>` | Receives data, processes it, and returns a result | `<beanName>-in-0`, `<beanName>-out-0` |
| `Consumer<T>` | Receives and processes data, returns no output | `<beanName>-in-0` |

Binding names are formed from the bean name and the input/output port index. For example, a bean named `validateOrder` has the input binding `validateOrder-in-0` and the output binding `validateOrder-out-0`.

If an application has only one eligible function bean, the framework can typically auto-detect and activate it. When an application has multiple `Supplier`, `Function`, or `Consumer` beans, explicitly declaring `spring.cloud.function.definition` identifies exactly which functions participate in processing. This also makes the configuration easier to read and more stable as the project grows.

Distinguish between three separate tasks:

1. Declare function beans to hold business logic.
2. Select one or more beans using `spring.cloud.function.definition`.
3. Map the generated bindings to destinations using `spring.cloud.stream.bindings`.

## 2. Where Names in the Definition Come From

The function name in the definition is the Spring bean name. For a `@Bean` method, the method name is the default bean name:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BasicOrderFunctionConfiguration {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim();
    }

}
~~~

In this example, the bean name is `normalizeOrder`, so it can be selected with:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
~~~

If an explicit bean name is specified, the definition must use that name:

~~~java
import org.springframework.context.annotation.Bean;

@Bean("normalize")
Function<String, String> normalizeOrder() {
    return value -> value.trim();
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: normalize
~~~

A Java class name, destination name, or binding name does not substitute for the bean name in the definition property. When the application does not activate the expected function, check the exact bean name in the Spring `ApplicationContext` first.

## 3. Selecting a Single Function

For a single function processing orders, declare:

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SingleOrderFunctionConfiguration {

    @Bean
    Function<String, String> validateOrder() {
        return order -> {
            if (order == null || order.isBlank()) {
                throw new IllegalArgumentException("Order must not be blank");
            }
            return order.trim();
        };
    }
}
~~~

Full configuration in `application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder

    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.raw
          group: order-validator
          content-type: text/plain

        validateOrder-out-0:
          destination: orders.validated
          content-type: text/plain
~~~

The application receives data from the `orders.raw` destination, passes the payload through the `validateOrder` function, and sends the result to `orders.validated`. The definition property only selects the function; the two destinations and the consumer group are configured in the bindings section.

If you rename the bean method from `validateOrder` to `checkOrder`, you must update both the definition and the corresponding bindings to `checkOrder-in-0` and `checkOrder-out-0`. Changing only one place can prevent the application from finding the function or applying the intended binding configuration.

## 4. Activating Multiple Independent Functions with a Semicolon

Use a semicolon (`;`) to select multiple independent functions within the same application. The functions are activated separately, each with its own bindings based on its bean name.

Example declaring four beans:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;
import java.time.Instant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class IndependentOrderFunctions {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim();
    }

    @Bean
    Function<String, String> maskOrder() {
        return value -> value.replaceAll("\\d", "*");
    }

    @Bean
    Consumer<String> auditOrder() {
        return value -> System.out.println("Audit order: " + value);
    }

    @Bean
    Supplier<String> heartbeat() {
        return () -> Instant.now().toString();
    }
}
~~~

Selecting all four beans:

~~~yaml
spring:
  cloud:
    function:
      definition: "normalizeOrder;maskOrder;auditOrder;heartbeat"

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        normalizeOrder-out-0:
          destination: orders.normalized
          content-type: text/plain

        maskOrder-in-0:
          destination: orders.to-mask
          group: order-masker
          content-type: text/plain
        maskOrder-out-0:
          destination: orders.masked
          content-type: text/plain

        auditOrder-in-0:
          destination: orders.audit
          group: order-auditor
          content-type: text/plain

        heartbeat-out-0:
          destination: system.heartbeat
          content-type: text/plain
~~~

These bindings operate independently:

- `normalizeOrder` receives data from `orders.raw` and publishes the result to `orders.normalized`.
- `maskOrder` receives data from `orders.to-mask` and publishes the result to `orders.masked`.
- `auditOrder` receives data from `orders.audit` and performs the audit task, with no output binding.
- `heartbeat` is invoked by the poller and publishes the current timestamp to `system.heartbeat` via its output binding.

A Supplier is invoked repeatedly according to the poller interval while the application is running, so the heartbeat example emits multiple timestamps. For real event sources, define an appropriate emission interval and ensure each poll does not repeat a business operation that should only execute once.

The semicolon does not pass the output of the preceding function into the input of the next function. It only instructs the framework to activate multiple separate functions. If the goal is to chain processing steps into a sequential flow, use composition with the pipe operator (`|`).

## 5. Combining Functions with the Pipe Operator

Use the `|` operator to compose type-compatible functions into a single composite function. The output of the preceding function becomes the input of the next function.

Example:

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderPipelineFunctions {

    @Bean
    Function<String, String> trimOrder() {
        return value -> value.trim();
    }

    @Bean
    Function<String, String> uppercaseOrder() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimOrder|uppercaseOrder"

    stream:
      bindings:
        "trimOrder|uppercaseOrder-in-0":
          destination: orders.raw
          group: order-transformer
          content-type: text/plain

        "trimOrder|uppercaseOrder-out-0":
          destination: orders.normalized
          content-type: text/plain
~~~

With the input message:

~~~text
  order-created  
~~~

The `trimOrder` function strips leading and trailing whitespace. The result is passed directly to `uppercaseOrder`, and then the output binding sends the string `ORDER-CREATED` to the `orders.normalized` destination.

The bindings of a composite function use the composition name, formatted as `trimOrder|uppercaseOrder-in-0` and `trimOrder|uppercaseOrder-out-0`. When a YAML key contains `|`, wrap the entire key in double quotes so the configuration remains readable and avoids confusion with YAML syntax.

Composed functions must have compatible output and input types. For instance, `Function<String, Integer>` can be chained with `Function<Integer, Long>`; it cannot be chained directly with `Function<Order, String>` without an appropriate conversion step.

Composition can also end with a Consumer to process the result without emitting an output, or start with a Supplier when data needs to be produced and passed through Function steps. Regardless of how many steps a composition has, from the binding perspective it remains a single composite function with corresponding input/output ports.

## 6. Combining Both: Independent Functions and Composition

Both forms can be combined in a single definition. The `|` operator chains functions within a pipeline; `;` separates independent function groups.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: "trimOrder|uppercaseOrder;auditOrder"

    stream:
      bindings:
        "trimOrder|uppercaseOrder-in-0":
          destination: orders.raw
          group: order-transformer
          content-type: text/plain
        "trimOrder|uppercaseOrder-out-0":
          destination: orders.normalized
          content-type: text/plain
        auditOrder-in-0:
          destination: orders.audit
          group: order-auditor
          content-type: text/plain
~~~

Here, `trimOrder|uppercaseOrder` is a pipeline receiving from `orders.raw` and publishing to `orders.normalized`. `auditOrder` is an independent function receiving from `orders.audit`. Both groups are activated within the same application.

Name beans clearly to reflect their responsibilities and keep the definition structure readable. When a composition chain grows long, break the logic into small functions with explicit input/output types. This makes it easier to test individual steps and pinpoint failures.

## 7. Distinguishing Definition from Binding and Destination

Three layers of configuration are often confused:

| Component | Question Answered | Example |
|---|---|---|
| Function bean | Where does the processing logic live? | `normalizeOrder()` |
| `spring.cloud.function.definition` | Which beans are activated? | `normalizeOrder` |
| `spring.cloud.stream.bindings` | Which destination does an input/output port connect to? | `normalizeOrder-in-0.destination: orders.raw` |
| Binder | Which middleware is it connected to? | Kafka, RabbitMQ, or Pulsar binder |

For example, the same `normalizeOrder` function can be mapped to a Kafka topic locally and a RabbitMQ destination in a test environment by swapping the binder and connection configuration. Both the function logic and the bean name can remain unchanged.

Do not put a topic name in `spring.cloud.function.definition`. For instance, `definition: orders.raw` is only valid if the Spring context actually contains a function bean named `orders.raw`, which is rarely the intended setup.

## 8. Configuration by Profile and Environment Variables

You can reuse the same function definition across multiple environments while changing destinations, groups, or brokers per profile.

Example `application.yml` file:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: ${ORDERS_INPUT:orders.raw}
          group: ${ORDERS_GROUP:order-normalizer}
          content-type: text/plain
        normalizeOrder-out-0:
          destination: ${ORDERS_OUTPUT:orders.normalized}
          content-type: text/plain
~~~

You can override environment variables when running the application:

~~~bash
ORDERS_INPUT=orders.incoming ORDERS_OUTPUT=orders.cleaned ./mvnw spring-boot:run
~~~

With PowerShell:

~~~powershell
$env:ORDERS_INPUT = "orders.incoming"
$env:ORDERS_OUTPUT = "orders.cleaned"
.\mvnw.cmd spring-boot:run
~~~

The environment variable corresponding to the definition property is `SPRING_CLOUD_FUNCTION_DEFINITION`. For example, you can select a different function at deployment time via environment configuration:

~~~bash
SPRING_CLOUD_FUNCTION_DEFINITION=normalizeOrder ./mvnw spring-boot:run
~~~

When using profiles, inspect the final resolved values after Spring Boot merges `application.yml`, profile files, environment variables, and command-line arguments. A profile might inadvertently override the definition, causing the application to activate a different function than expected.

## 9. Verifying Which Functions Are Actually Activated

When the application starts, inspect Spring Cloud Function and Spring Cloud Stream logs to verify the discovered functions, selected functions, and created bindings. Exact log content may vary depending on the version and log level.

You can enable verbose logging in development:

~~~yaml
logging:
  level:
    org.springframework.cloud.function: DEBUG
    org.springframework.cloud.stream: DEBUG
~~~

After startup, verify the following points:

1. The bean names in the definition exist in the Spring `ApplicationContext`.
2. Each selected function has the intended `Supplier`, `Function`, or `Consumer` type.
3. The generated binding names match the configuration keys under `spring.cloud.stream.bindings`.
4. Input bindings point to the right destination and consumer group.
5. Output bindings have the appropriate destination and content type.
6. The expected binder is selected and connected to the right broker.

If Actuator and the relevant endpoints are enabled, you can use binding/health details to aid status checks. Avoid exposing sensitive management endpoints publicly solely for debugging.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
|---|---|---|
| Function not found from definition | Wrong bean name, bean not component-scanned, or bean not created | Check `@Bean` method name, `@Component` name, and package scanning |
| Application has multiple functions but only one flow runs | Definition selects only one function or functions are not separated properly | Use `;` for multiple independent functions |
| Output of preceding function does not enter the next function | Used `;` instead of composition | Use `functionA|functionB` if data types are compatible |
| Composition fails to initialize | Output type and input type of adjacent steps are incompatible | Check generics and actual payload types of each function |
| Binding not found | Binding key does not match function name or composition name | Check `-in-0`, `-out-0` suffixes and bean name |
| Right function selected but receives no messages | Destination, group, binder, or broker is misconfigured | Check `spring.cloud.stream.bindings` configuration and binder logs |
| Works locally but staging selects a different function | A profile or environment variable overrides the definition | Check effective configuration at startup |
| Consumer has no output | Bean is a Consumer, so it only has an input binding | Check processing intent; a Consumer does not create an output binding |

A few rules to avoid mistakes:

- Use `spring.cloud.function.definition`, not `spring.cloud.stream.function.definition`.
- Use the exact bean name, including any explicit name declared in `@Bean("...")`.
- Use `;` when activating multiple independent functions.
- Use `|` when chaining the output of one function into the input of the next.
- Update bindings whenever you rename a bean or composition.
- Verify the effective configuration from profiles and environment variables before concluding that a function is not working.

## 11. Testing Selection and Composition

You can test each bean as plain Java logic:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class IndependentOrderFunctionsTest {

    @Test
    void normalizeOrderRemovesSurroundingSpaces() {
        IndependentOrderFunctions functions = new IndependentOrderFunctions();
        assertEquals("order-100", functions.normalizeOrder().apply("  order-100  "));
    }
}
~~~

For Spring Cloud Stream flows, use the test binder to verify input and output bindings without a real broker. For function composition, send a message to the composition's input binding and assert the result at the composition's output binding.

A test plan should include:

- Running the application with a single function and verifying the expected input/output bindings.
- Running with multiple semicolon-separated functions and verifying each function has its own bindings.
- Running a composition using `|` and verifying execution order and final output.
- Testing incompatible types during development to catch wiring errors early.
- Starting with different profiles and verifying the final resolved definition matches expectations.
- Running integration tests against a real broker to verify destinations, groups, and delivery behavior.

The test binder proves that the application wires functions to bindings as configured. It does not replace real-broker testing for partitions, rebalancing, acknowledgments, retries, transactions, or DLQs.

## 12. Practice Sequence and Completion Criteria

| Step | Practice | Expected Outcome |
|---|---|---|
| 1. Declare beans | Create one Supplier, one Function, and one Consumer | Know the Spring bean names and function types |
| 2. Select one function | Set `spring.cloud.function.definition` to a single bean name | Only that function is activated |
| 3. Select multiple functions | Separate names with semicolons | Functions operate independently with separate bindings |
| 4. Composition | Chain two Functions with `|` | Output of the first step becomes input of the second |
| 5. Map bindings | Configure destination, group, and content type | Messages route to the right destinations |
| 6. Test | Use unit tests, the test binder, and a real broker | Distinguish logic errors, wiring errors, and broker errors |
| 7. Deploy | Verify profiles and environment variables | Running environment activates the intended functions |

The lesson is complete when you can explain and configure all three cases on your own: a single function, multiple independent functions, and a multi-function pipeline. You should also be able to determine the binding names generated from a bean name or composition and map those bindings to the appropriate destinations.

## 13. Official References

- [Spring Cloud Function — Function Catalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — functional model and function bean registration.
- [Spring Cloud Function — Function Composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-composition) — how to compose functions.
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — binding names derived from Supplier, Function, and Consumer.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — integrating the functional model with bindings and binders.
- [Spring Cloud Stream — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — configuring destination, group, and content type.
- [Spring Boot — Externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — configuration via profiles, environment variables, and command-line arguments.
