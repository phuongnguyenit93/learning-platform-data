# Application Starts Up but Function Is Not Bound

A Spring Boot application can start up successfully while the function still fails to read or write messages through the broker. The root cause is often not in the message-processing logic itself, but in an earlier step: the function bean has not been created, Spring Cloud Function has not selected the right bean, Spring Cloud Stream has not created the binding, or the binding has been created but cannot connect to the destination.

It is necessary to separate three states:

1. **Function bean exists:** The Spring ApplicationContext has registered a Supplier, Function, or Consumer bean.
2. **Function is selected:** Spring Cloud Function knows which bean is used as the message handler.
3. **Binding is active:** Spring Cloud Stream has connected the function's input/output to the destination through the binder.

An application can reach the first state without reaching the other two. A binding can also exist yet receive no messages due to a misconfigured destination, group, broker permissions, or serializer settings. This lesson provides a step-by-step verification process from bean discovery to the broker to pinpoint the exact failing layer.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between a function bean, function definition, binding, and destination.
- Check whether a bean is picked up by Spring component scan and registered in the ApplicationContext.
- Select the right function using spring.cloud.function.definition.
- Recognize issues when multiple Suppliers/Functions/Consumers exist in the same application.
- Derive binding names from the function name and signature type.
- Configure destination, group, binder, and binding aliases with the correct names.
- Distinguish between Supplier, Function, Consumer, and reactive signatures.
- Verify binder dependencies, provisioning, credentials, and broker connectivity.
- Use startup logs, Actuator bindings, and Test Binder to isolate the issue.
- Follow an ordered diagnostic procedure and verify with an integration test.

## 1. Understand the Components That Need to Be Bound

In Spring Cloud Stream, a function is the code that processes data; a binding is the bridge between the function and the messaging system; a destination is the topic, queue, or exchange on the broker; and a binder is the implementation that communicates with the broker.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] --> B["Function bean"]
    B --> C["spring.cloud.function.definition"]
    C --> D["Spring Cloud Stream binding"]
    D --> E["Binder implementation"]
    E --> F["Kafka topic / RabbitMQ exchange-queue / Pulsar topic"]
    F --> G["Message delivery"]
    G --> H["Function invocation"]
~~~

A function can exist without being selected. A selected function may lack a suitable binder. A binding may be created yet remain in the STOPPED state or fail to connect to the broker.

Therefore, when the application starts up without any messages flowing, do not immediately conclude that the function is not running. First, identify the last layer that actually worked.

## 2. Check Whether the Function Bean Is Registered

Spring Cloud Stream uses Spring Cloud Function. The recognized functional bean types include:

- java.util.function.Supplier: produces outbound messages.
- java.util.function.Function: receives inbound messages and produces outbound messages.
- java.util.function.Consumer: receives inbound messages and produces no output.

Example of a simple function:

~~~java
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderStreamApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderStreamApplication.class, args);
    }

    @Bean
    public Function<String, String> normalizeOrder() {
        return value -> value.trim().toUpperCase();
    }
}
~~~

The function bean name in this example is normalizeOrder, taken from the @Bean method name. Spring Cloud Stream can use this bean as a message handler when the functional model is enabled and the function is selected.

### Reasons a Bean Fails to Appear

**Configuration is outside component scan**

By default, Spring Boot scans the package containing the @SpringBootApplication class and its subpackages. If the configuration class declaring the function resides outside that scope, the bean method may not be registered.

For example:

~~~text
com.acme.orders
  OrderStreamApplication.java
  functions/
    OrderFunctions.java

com.acme.shared
  SharedFunctionConfiguration.java
~~~

If SharedFunctionConfiguration lies outside the scanned package tree, include it in the scan scope or import the configuration explicitly:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import java.util.function.Consumer;

@Configuration
class SharedFunctionConfiguration {

    @Bean
    Consumer<String> auditOrder() {
        return value -> System.out.println("Audit: " + value);
    }
}

@SpringBootApplication
@Import(SharedFunctionConfiguration.class)
class OrderStreamApplication {
}
~~~

Do not arbitrarily widen component scanning to the entire classpath. Identify the package containing the function configuration and bring that specific package into the ApplicationContext.

**Bean is conditional**

Annotations such as @Profile, @ConditionalOnProperty, @ConditionalOnClass, or @ConditionalOnBean can cause a bean to be created only in a specific environment.

~~~java
@Bean
@Profile("messaging")
Function<String, String> normalizeOrder() {
    return String::trim;
}
~~~

If the messaging profile is not activated, this bean does not exist. Check the active profiles, environment variables, and actual property sources of the runtime environment.

**Bean name differs from the configured name**

~~~java
@Bean("normalize")
Function<String, String> normalizeOrder() {
    return String::trim;
}
~~~

The bean name here is normalize. If the function definition configuration points to normalizeOrder, Spring Cloud Function will not find the bean under that name. The name explicitly specified in @Bean takes effect.

Bean names are case-sensitive. Verify the exact registered name and the name in configuration.

**Incorrect function type declaration**

Ensure the bean actually has type Supplier, Function, or Consumer. An ordinary service method does not automatically become a function just because it takes parameters or returns data.

You should declare concrete generic types:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return orderService::accept;
}
~~~

Avoid raw types such as Function or Consumer unless necessary. Generic types help the framework determine payload types and choose the appropriate conversion mechanism.

### Inspecting Beans from the ApplicationContext

You can add a temporary probe in a development environment to check which functional beans have been registered:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class FunctionBeanProbe {

    private static final Logger log =
        LoggerFactory.getLogger(FunctionBeanProbe.class);

    @Bean
    ApplicationRunner reportFunctions(ApplicationContext context) {
        return args -> {
            log.info("Supplier beans: {}",
                context.getBeansOfType(Supplier.class).keySet());
            log.info("Function beans: {}",
                context.getBeansOfType(Function.class).keySet());
            log.info("Consumer beans: {}",
                context.getBeansOfType(Consumer.class).keySet());
        };
    }
}
~~~

This probe only confirms that the bean is present in the ApplicationContext. It does not prove that the function has been selected by Spring Cloud Stream or that the binding is active. After diagnosing, remove the probe if it is no longer needed.

## 3. Select the Right Function with spring.cloud.function.definition

If the application has only one functional bean, Spring Cloud Stream can auto-discover and bind it. However, the Spring documentation recommends declaring spring.cloud.function.definition explicitly to avoid auto-discovering the wrong bean or changing behavior as the application grows.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
~~~

A common mistake is misconfiguring the property as spring.cloud.stream.function.definition. The property used to select functional beans is:

~~~text
spring.cloud.function.definition
~~~

### When There Are Multiple Function Beans

Suppose the application has two independent functions:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

When multiple functional beans exist, you must specify which function(s) to bind. To bind both functions independently, use a semicolon:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase;reverse
~~~

In that case, each function has its own set of bindings:

- uppercase-in-0 and uppercase-out-0.
- reverse-in-0 and reverse-out-0.

### Distinguish Multiple Independent Functions from Composition

A semicolon selects multiple independent functions. A pipe composes multiple functions into a single pipeline:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder|enrichOrder|validateOrder
~~~

In this example, messages flow sequentially through normalizeOrder, enrichOrder, and validateOrder. Composed functions must have output types compatible with the input type of the next function.

If you only want one function to run independently, do not include other function names in the definition. If you want to compose functions, use a pipe and verify the exact processing order.

### Auto-Discovery Disabled

Spring Cloud Stream provides the property:

~~~yaml
spring:
  cloud:
    stream:
      function:
        autodetect: false
~~~

When set to false, automatic function discovery is disabled. Without a matching function definition or explicitly created bindings, the application can start without any bound functions.

Search for this property in application.yml, profile-specific configurations, command-line arguments, and environment variables. A value from the deployment environment can override settings in configuration files.

## 4. Check Function Signature and Message Direction

A function lacking a corresponding input/output binding may lead operators to believe it is not bound.

| Bean Type | Default Binding | Direction of Operation |
|---|---|---|
| Supplier<T> | supplierName-out-0 | Emits messages only |
| Consumer<T> | consumerName-in-0 | Receives messages only |
| Function<T, R> | functionName-in-0 and functionName-out-0 | Receives then emits messages |

Consumer example:

~~~java
@Bean
Consumer<OrderCreated> auditOrder() {
    return event -> auditService.record(event);
}
~~~

A Consumer only has input. Having no output binding is the expected behavior.

Supplier example:

~~~java
@Bean
Supplier<OrderCreated> orderSource() {
    return () -> orderService.nextPendingOrder();
}
~~~

A Supplier only has output. It does not wait for a message from an input topic.

Function example:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return orderService::accept;
}
~~~

A Function has both input and output.

### A Supplier Is Not a Listener

A Supplier does not subscribe to a destination. An imperative Supplier is invoked by a default poller, typically once per second. The poller can be adjusted:

~~~yaml
spring:
  integration:
    poller:
      fixed-delay: 2000
      initial-delay: 500
~~~

When using per-binding polling configuration, you can configure it under the output binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderSource-out-0:
          producer:
            poller:
              fixed-delay: 2000
~~~

A reactive Supplier returning a continuous Flux is normally invoked once to create the stream. If a Supplier returns a finite Flux that needs to be invoked periodically, use @PollableBean according to the guidance for your Spring Cloud Stream version.

If the application has a Supplier while expecting messages on an input topic, the signature design does not match the goal. Use a Function or Consumer for message-receiving flows.

### Reactive Functions Have a Different Lifecycle from Imperative Functions

With Function<Flux<T>, Flux<R>>, the framework invokes the function to set up the reactive pipeline. Reactor then processes the items in the stream. Do not expect the apply method to be called again once per message.

Example:

~~~java
@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> acceptOrders() {
    return events -> events.map(orderService::accept);
}
~~~

When using Consumer<Flux<T>>, the application must ensure the subscription is established properly. In many cases, the Spring Cloud Stream documentation recommends using Function<Flux<T>, Mono<Void>> to represent reactive processing completion clearly:

~~~java
@Bean
Function<Flux<OrderCreated>, Mono<Void>> auditOrders() {
    return events -> events
        .doOnNext(auditService::record)
        .then();
}
~~~

A reactive function being invoked only once at pipeline initialization does not mean the function is unbound. Inspect the subscription, signals, and processing results inside the stream.

## 5. Determine the Exact Binding Name

In the functional model, binding names are generated from the function bean name:

- Input: functionName-in-index.
- Output: functionName-out-index.

For a function with one input and one output, the default index is 0.

Example:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return orderService::accept;
}
~~~

Binding names:

~~~text
acceptOrder-in-0
acceptOrder-out-0
~~~

A binding name is not necessarily the topic, queue, or exchange name. The binding name is an internal name used for configuration; the destination is the external resource name.

Correct configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          group: billing-service
        acceptOrder-out-0:
          destination: orders.accepted
~~~

A very common mistake is writing:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders.created:
          destination: orders.created
~~~

In the incorrect example, orders.created is used as the binding name, whereas the function actually generates acceptOrder-in-0. These two names do not bind to each other automatically.

### Functions with Multiple Inputs or Outputs

With multiple inputs/outputs, the index increments in order:

- processOrder-in-0.
- processOrder-in-1.
- processOrder-out-0.
- processOrder-out-1.

Check the function signature and the corresponding binding names. Do not arbitrarily change indices or infer binding names from destinations.

### Binding Aliases

You can map default binding names to more descriptive names using:

~~~yaml
spring:
  cloud:
    stream:
      function:
        bindings:
          acceptOrder-in-0: ordersInput
          acceptOrder-out-0: ordersOutput
      bindings:
        ordersInput:
          destination: orders.created
          group: billing-service
        ordersOutput:
          destination: orders.accepted
~~~

After declaring aliases, subsequent binding configurations must use the aliases ordersInput and ordersOutput. If you still configure the destination under acceptOrder-in-0, the application may read configuration for a different binding than the actual one.

When tracing the relationship between an alias and a function, check the spring.cloud.stream.function.bindings property along with the function bean name.

## 6. Check the Binder and Destination

A function can be selected properly yet fail to connect to the broker if the binder is missing from the classpath or misconfigured.

Spring Cloud Stream auto-detects binder implementations present on the classpath. For example, an application using Kafka requires the Kafka binder dependency; an application using RabbitMQ requires the RabbitMQ binder dependency.

Maven example for the Kafka binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
~~~

Maven example for the RabbitMQ binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-rabbit</artifactId>
</dependency>
~~~

If only spring-cloud-stream core is present without the corresponding binder implementation, the function may exist without a suitable binder to connect to the broker. Check the runtime dependencies of the packaged artifact, not just the dependencies shown in the IDE.

### Single Binder on the Classpath

If only one binder implementation is present, the framework can select it automatically. Still, verify that the binder matches the target runtime environment.

### Multiple Binders on the Classpath

If multiple binders are present, specify a default binder or a binder per binding:

~~~yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        acceptOrder-in-0:
          binder: kafka
          destination: orders.created
          group: billing-service
        acceptOrder-out-0:
          binder: rabbit
          destination: orders.accepted
~~~

If multiple binders are configured but a binder name does not exist or does not match the registered configuration, the binding will not work. Check both the binder name and binder type.

### Destination and Broker Permissions

If the binding is created but does not receive or send messages, check:

- Does the destination have the exact topic, queue, or exchange name?
- Are the broker host and port correct?
- Do the credentials have read/write permissions or resource declaration permissions?
- Does the topic/queue exist if automatic provisioning is disabled?
- Are the Pulsar namespace/tenant/topic correct?
- Do the RabbitMQ exchange and queue have the matching binding/routing key?
- Is the Kafka consumer group reading the right topic and offset?

The destination may default to the binding name if left unconfigured. In production, declaring destinations explicitly avoids relying on default names.

Group applies only to input bindings. Omitting group typically creates an anonymous consumer depending on the binder; this does not mean the function is unbound. Group affects consumer identity and message distribution, not the function name.

## 7. Distinguish Function Bindings from StreamBridge

Not every Spring Cloud Stream application needs a Supplier or Function bean.

If the data source is a REST endpoint, scheduler, or external system, StreamBridge can be used to send messages:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderCreated event) {
        return streamBridge.send("ordersOutput", event);
    }
}
~~~

In this case, a Supplier bean is not needed just to produce output. StreamBridge can create a dynamic output binding on the first send call.

To create the output binding immediately at application startup, declare:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersOutput
      bindings:
        ordersOutput:
          destination: orders.created
~~~

An explicitly created binding does not use the -out-0 suffix because it is not generated from a function bean.

When investigating, determine whether the application uses functional binding or explicit/dynamic binding. Looking only for function beans in an application that uses StreamBridge can lead to mistakenly concluding that a missing function is an error.

## 8. Enable Logging to Observe Discovery and Binding

When configuration behavior is unclear, increase log levels selectively:

~~~yaml
logging:
  level:
    org.springframework.cloud.function: DEBUG
    org.springframework.cloud.stream: DEBUG
    org.springframework.integration: DEBUG
    org.springframework.messaging: DEBUG
~~~

These log groups help inspect:
- Which functions are registered.
- Which function definition is selected.
- Which binding names are created.
- Which binder is used.
- Which destinations are configured.
- Connection or provisioning errors.
- Message conversion and channel lifecycle.

Do not enable DEBUG across the entire application in production unless necessary. Detailed logs can generate high volume and expose sensitive configuration data. Enable them only during diagnosis, then restore appropriate log levels.

### Symptoms to Look For

| Symptom | Interpretation |
|---|---|
| Function bean does not appear in ApplicationContext | Component scan, profile, or bean conditional issue |
| Multiple functions exist without a clear definition | Framework does not know which function to bind |
| Expected binding name is missing | Function not selected or signature does not produce that binding direction |
| Binding exists but binder fails | Dependency, binder selection, or connection configuration |
| Binding is in STOPPED state | Binding was created but its lifecycle has not started |
| Binding is RUNNING but no messages arrive | Check destination, group, offset, routing, and producer |
| Messages are received but function produces no output | Consumer/function logic, exception, conversion, or function is a Consumer |
| Supplier binding exists but emits no messages | Poller, Supplier returning null/empty, or reactive stream not triggered as expected |

## 9. Use Actuator to Inspect Actual Bindings

Spring Cloud Stream supports an Actuator endpoint to inspect and control the binding lifecycle.

You need Spring Boot Actuator and the appropriate web dependency, then expose the bindings endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,bindings
~~~

View all bindings:

~~~text
GET /actuator/bindings
~~~

View a single binding:

~~~text
GET /actuator/bindings/acceptOrder-in-0
~~~

The endpoint can show the binding name, input/output direction, group, and lifecycle state depending on the binder. If the binding does not appear, go back and verify function discovery, function definition, and binding naming.

If the binding appears as STOPPED, check lifecycle configuration and why the binding has not started. With the Kafka Streams binder, auto-startup can be configured for consumer bindings to actively start the processor; this is a binder-specific scenario, not a universal fix for all binders.

The bindings endpoint can control binding state. Expose it only on a protected management network and restrict access permissions. Do not expose this control endpoint to the public Internet.

## 10. Test Functions and Bindings with the Test Binder

Spring Integration Test Binder allows testing functions and bindings inside the JVM without a real broker.

Add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Example function test:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = OrderStreamTests.TestApplication.class,
    properties = "spring.cloud.function.definition=normalizeOrder"
)
class OrderStreamTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void normalizeOrderIsBound() {
        input.send(new GenericMessage<byte[]>(
            "  order-1001  ".getBytes(StandardCharsets.UTF_8)));

        Message<byte[]> result = output.receive();

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("ORDER-1001");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {

        @Bean
        Function<String, String> normalizeOrder() {
            return value -> value.trim().toUpperCase();
        }
    }
}
~~~

In real tests, input/output configuration and payloads must match the function under test. If there are multiple functions, pass spring.cloud.function.definition in the test to verify the exact selected function.

With multiple bindings, InputDestination.send and OutputDestination.receive have overloads that let you specify the binding name. This is useful for catching incorrect binding names or aliases.

Test Binder helps confirm:
- The function bean can be selected.
- Input/output bindings are created.
- Messages can pass through the function.
- Conversion and function logic work in the test environment.

Test Binder does not verify that the real broker has valid topics/queues, credentials, TLS, network connectivity, or provisioning. After Test Binder tests pass, you still need integration tests against Kafka, RabbitMQ, or Pulsar respectively.

## 11. Ordered Diagnostic Procedure

When the application starts up but the function is not bound, follow this sequence:

1. **Confirm the bean:** check whether the ApplicationContext contains the expected Supplier, Function, or Consumer.
2. **Confirm the bean name:** match the @Bean method name, explicitly declared bean name, and function definition.
3. **Confirm selection:** set spring.cloud.function.definition explicitly; check whether multiple functions or autodetect=false are present.
4. **Confirm the signature:** verify Supplier/Function/Consumer and input/output directions.
5. **Confirm binding names:** derive -in-0 and -out-0 names from the bean name; check aliases.
6. **Confirm the binder:** verify that the binder dependency is on the runtime classpath and the binder name is valid.
7. **Confirm the destination:** check topic, queue, exchange, namespace, group, and access permissions.
8. **Confirm lifecycle:** verify whether the binding appears and is RUNNING.
9. **Confirm the message path:** send a test message and follow logs/traces through the function.
10. **Confirm against the real broker:** run an integration test with the production binder.

~~~mermaid
flowchart TD
    A["Application started"] --> B{"Does the function bean exist?"}
    B -->|No| C["Check component scan, profile, @Bean"]
    B -->|Yes| D{"Is the function selected?"}
    D -->|No| E["Check spring.cloud.function.definition and autodetect"]
    D -->|Yes| F{"Does the binding appear?"}
    F -->|No| G["Check signature and binding name/alias"]
    F -->|Yes| H{"Do the binder and destination work?"}
    H -->|No| I["Check binder dependency, configuration, permissions, and provisioning"]
    H -->|Yes| J{"Is binding RUNNING and receiving messages?"}
    J -->|No| K["Check lifecycle, group, topic, offset, and routing"]
    J -->|Yes| L["Check conversion, function exceptions, and output"]
~~~

Do not change multiple properties at the same time. After each step, record the state of the bean, function definition, binding name, binder, and destination. This makes it clear which exact change restored the binding.

## 12. Common Error Scenarios

| Symptom | Common Cause | Resolution |
|---|---|---|
| App runs but no function bean exists | Configuration is outside component scan | Move or import the configuration properly |
| Function bean exists but no binding | Multiple functions and missing definition | Specify spring.cloud.function.definition |
| Only one function yet not auto-bound | autodetect is disabled | Set definition or re-enable auto-discovery |
| Function definition cannot find bean | Wrong name or case mismatch | Use the exact bean name |
| Consumer has binding but expects output | Consumer has no output | Use Function if returning a message is needed |
| Supplier does not receive inbound messages | Supplier is a source only | Switch to Function/Consumer if input is needed |
| Function has input but no output | Function is actually declared as Consumer | Fix bean type if emitting output is needed |
| Binding not found under destination name | Confusing destination with binding name | Use functionName-in-0/out-0 then map destination |
| Alias changed but old configuration remains | Properties still use the old binding name | Move all properties to the alias |
| Function has multiple inputs/outputs with wrong flow | Wrong index used | Check parameter order and binding indices |
| Binder not found | Missing runtime binder dependency | Add the appropriate binder and check packaged artifact |
| Multi-binder selects wrong binder | Missing default-binder or binder on binding | Specify binder explicitly |
| Binding created but fails to connect to broker | Wrong credentials, TLS, network, or endpoint | Check broker connection and permissions |
| Binding RUNNING but receives no messages | Wrong destination, group, offset, or routing | Check broker-side message flow |
| Supplier emits no data | Poller not running or Supplier returns null | Check poller, output binding, and return value |
| Reactive Supplier runs only once | Reactive stream is created once | Check stream subscription; use @PollableBean for finite polling |
| Reactive Consumer does not process | Flux is not subscribed | Use Function<Flux<T>, Mono<Void>> or proper subscription |
| Test Binder passes but production fails | Broker/provisioning/security differences | Run integration test against real broker |
| Actuator lacks bindings | Missing Actuator/web or endpoint not exposed | Add dependency and exposure property |

## 13. Hands-On Exercise: Restoring the acceptOrder Function

Scenario: the Order Stream application starts up successfully, but no messages flow from topic orders.created through the acceptOrder function to orders.accepted.

1. Confirm OrderStreamApplication is the main Spring Boot class.
2. Check that OrderFunctions is inside a scanned package.
3. Confirm a bean named acceptOrder has type Function<OrderCreated, OrderAccepted>.
4. Set spring.cloud.function.definition=acceptOrder.
5. Check that spring.cloud.stream.function.autodetect=false is not disabling the required mechanism.
6. Check the binding names acceptOrder-in-0 and acceptOrder-out-0.
7. Configure destinations orders.created and orders.accepted.
8. Check the Kafka binder dependency and brokers configuration.
9. Check group billing-service and topic read permissions.
10. Enable DEBUG for Spring Cloud Function and Spring Cloud Stream.
11. Open Actuator bindings and confirm both bindings exist in the RUNNING state.
12. Use Test Binder to send OrderCreated and verify OrderAccepted is emitted.
13. Run an integration test with real Kafka.
14. Check offset, consumer group, serialization, and broker-side topic.
15. Disable DEBUG and narrow Actuator exposure once finished.

Acceptance Checklist:

| Item | Result to Confirm |
|---|---|
| Bean registration | acceptOrder appears in ApplicationContext |
| Function selection | definition points to acceptOrder |
| Function signature | Function has matching input and output |
| Binding names | acceptOrder-in-0 and acceptOrder-out-0 |
| Destinations | orders.created and orders.accepted |
| Binder | Kafka binder is on runtime classpath |
| Consumer group | billing-service is configured correctly |
| Lifecycle | Both bindings appear and are RUNNING |
| Test Binder | Message passes through function successfully |
| Broker integration | Real messages are received and emitted |
| Logs | No discovery, binding, or provisioning errors remain |
| Security | Actuator bindings is protected and not public |

## Conclusion

When a Spring Cloud Stream application starts up but a function is not bound, check across three layers: whether the bean exists, whether the function is selected, and whether the binding is active. The function name, spring.cloud.function.definition property, Supplier/Function/Consumer signature, and binding naming rules determine whether the framework can create the right bindings.

Next, verify binder dependencies, destination, group, broker permissions, and binding lifecycle. Test Binder helps validate functions and bindings inside the JVM; integration tests with a real broker validate the end-to-end pipeline. Separating each layer prevents changing broker configuration to fix bean discovery errors or modifying functions when the binding is already working.

## References

- [Spring Cloud Stream 5.0 – Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream – Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream – Bindings](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/bindings.html)
- [Spring Cloud Stream – Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream – Explicit Binding Creation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/explicit-binding-creation.html)
- [Spring Cloud Stream – Testing with Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream – Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/index.html)
- [Spring Cloud Function – Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
