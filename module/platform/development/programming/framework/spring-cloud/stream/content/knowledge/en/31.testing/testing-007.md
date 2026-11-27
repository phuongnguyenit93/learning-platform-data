# Testing Function Composition, Routing, and StreamBridge

In a Spring Cloud Stream application, a processing flow can be assembled from multiple small functions, select handlers based on message information, or send messages to destinations determined at runtime. These three capabilities often appear together: function composition builds pipelines, routing selects processing branches, and StreamBridge connects an external data source to an output binding.

Testing must verify both the logic and how the framework wires these components together. A function may run properly when called directly, yet the composition binding may use the wrong name; a router may pick the wrong handler due to headers or expressions; StreamBridge may send to an unauthorized destination or lack the expected producer configuration.

Spring Cloud Stream provides the Spring Integration Test Binder for in-JVM testing without Kafka, RabbitMQ, or Pulsar. The Test Binder lets you send messages to input bindings and receive messages from output bindings. Afterwards, integration tests with a real broker verify middleware-dependent behaviors such as topic/queue provisioning, serialization, routing keys, partitions, ACLs, retries, and delivery semantics.

## 1. Distinguishing the Three Capabilities to Test

| Component | Role | What to Verify |
|---|---|---|
| Function composition | Chains multiple Suppliers/Functions/Consumers into a single handler. | Execution order, type conversion, input/output binding names, and final payload. |
| Event routing | Selects a target function/consumer or output destination based on messages/properties. | Route selection rules, headers, fallbacks, allowed destinations, and invalid route errors. |
| StreamBridge | Sends objects or Messages from REST, schedulers, callbacks, or non-binder sources to output bindings. | Binding/destination name, payload, headers, content type, send result, and dynamic binding creation behavior. |

Do not lump everything into one giant test right away. Testing functions individually catches business bugs fast; the Test Binder verifies in-application wiring; integration tests verify specific brokers and binders.

## 2. Setting Up Spring Integration Test Binder

The current Test Binder resides in the `spring-cloud-stream-test-binder` artifact. Declare the dependency in `test` scope so it does not become a production runtime binder.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~kotlin
testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
~~~

The dependency version should be managed by the Spring Cloud BOM matching your project's Spring Boot/Spring Cloud versions. Do not pick a test binder version from a different release train than the Spring Cloud Stream version in use.

To enable the binder in the test context, use `@EnableTestBinder`:

~~~java
@SpringBootTest
class OrderStreamTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

`InputDestination` represents input bindings in tests; `OutputDestination` lets you read messages sent by the application to output bindings. When the application has multiple inputs/outputs, pass the binding name or destination explicitly to `send` and `receive` so tests do not depend on binding order.

## 3. Testing Functions Directly Before Testing Bindings

Business logic should be separated from the binder so it can be tested with ordinary unit tests. Example:

~~~java
@Component
class OrderNormalizer {

    Order normalize(Order order) {
        return new Order(
            order.id().trim(),
            order.customerId().trim().toUpperCase(Locale.ROOT),
            order.amount()
        );
    }
}
~~~

The unit test only checks the function's output:

~~~java
@Test
void normalizesCustomerId() {
    OrderNormalizer normalizer = new OrderNormalizer();

    Order result = normalizer.normalize(
        new Order(" order-1 ", " cust-7 ", 125_000)
    );

    assertThat(result.id()).isEqualTo("order-1");
    assertThat(result.customerId()).isEqualTo("CUST-7");
    assertThat(result.amount()).isEqualTo(125_000);
}
~~~

Unit tests do not need to create a Spring context or test binder. Once the logic is sound, wrap it in a function bean and test the binding separately.

## 4. Composing Functions with `spring.cloud.function.definition`

Spring Cloud Function allows composing functions using the `|` operator or commas in the `spring.cloud.function.definition` property. Example:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase|addSuffix
~~~

With the two beans `uppercase` and `addSuffix`, the framework invokes `uppercase` first and passes the result to `addSuffix`. The composed chain is treated as a single function at runtime.

~~~java
@Configuration
class TextFunctions {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }

    @Bean
    Function<String, String> addSuffix() {
        return value -> value + "!";
    }
}
~~~

If the input is `hello`, the composed output is `HELLO!`.

### 4.1. Composition Binding Names

Default binding names for a composition are formed from the function names in composition order. For `uppercase|addSuffix`, the bindings are typically:

| Binding | Meaning |
|---|---|
| `uppercaseaddSuffix-in-0` | Input of the composed function. |
| `uppercaseaddSuffix-out-0` | Output of the composed function. |

When configuring destinations:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase|addSuffix
    stream:
      bindings:
        uppercaseaddSuffix-in-0:
          destination: text.raw
        uppercaseaddSuffix-out-0:
          destination: text.normalized
~~~

If the binding name is long or hard to read, you can alias the functional binding name via `spring.cloud.stream.function.bindings`. Once renamed, all configuration properties and tests must use the aliased name.

Do not confuse delimiters:

- `uppercase|addSuffix` composes two functions into one pipeline.
- `uppercase;reverse` selects two independent functions in the same application, each with its own input/output bindings.

### 4.2. Testing Composition with the Test Binder

The following test verifies both composition order and binding names:

~~~java
@SpringBootTest(
    classes = CompositionTest.TestApplication.class,
    properties = "spring.cloud.function.definition=uppercase|addSuffix"
)
class CompositionTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void appliesFunctionsInDeclaredOrder() {
        Message<byte[]> message = MessageBuilder
            .withPayload("hello".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        input.send(message, "uppercaseaddSuffix-in-0");

        Message<byte[]> result = output.receive(
            1_000,
            "uppercaseaddSuffix-out-0"
        );

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("HELLO!");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {

        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }

        @Bean
        Function<String, String> addSuffix() {
            return value -> value + "!";
        }
    }
}
~~~

The Test Binder uses in-JVM message channels, so no broker is required. `receive` with a timeout ensures tests fail clearly if output never arrives, instead of hanging indefinitely.

You should add cases for:

- The first function receiving invalid data.
- An intermediate function throwing an exception.
- The final function producing an empty or null payload per contract.
- Content types that do not match argument types.
- Whether required headers are preserved/transformed as expected.

By default, input headers are not all forwarded automatically to a function's output. If you need to keep headers, the function can accept `Message<?>` and build the output Message explicitly, or configure `copy-input-headers` for that function. Test critical business headers instead of assuming they always survive.

## 5. Composing Functions with Consumers or Suppliers

Spring Cloud Function supports several composition combinations:

| Composition | Resulting Type |
|---|---|
| Supplier + Function | Supplier |
| Supplier + Consumer | Runnable |
| Function + Function | Function |
| Function + Consumer | Consumer |

Not every pair can be composed. For example, a Consumer produces no output to feed into a subsequent Function. When composing a Function with a Consumer, the composition ends in a Consumer and has no output binding.

When testing a composition ending in a Consumer, verify side effects through a test collaborator (mock/fake/recorder) instead of waiting on `OutputDestination`. When a composition starts with a Supplier, control the poller or trigger mechanism; avoid letting tests rely on unintended default polling intervals.

With reactive functions, note that the function may be invoked once to construct the Publisher rather than once per message. If composing a reactive function with a Consumer, ensure the Consumer actually subscribes to and consumes the stream per the chosen model. Tests should verify subscription and Publisher completion/error signals.

## 6. Routing Messages to Functions or Consumers

`RoutingFunction` lets a single input binding receive messages and select a target function/consumer. Enable routing with:

~~~yaml
spring:
  cloud:
    stream:
      function:
        routing:
          enabled: true
~~~

The router's input binding is named `functionRouter-in-0`. Messages can carry one of two headers:

- `spring.cloud.function.definition`: name of the function/consumer or composition to invoke.
- `spring.cloud.function.routing-expression`: SpEL expression to determine the target function.

Example handlers:

~~~java
@Bean
Consumer<String> priorityHandler() {
    return value -> log.info("Priority order: {}", value);
}

@Bean
Consumer<String> standardHandler() {
    return value -> log.info("Standard order: {}", value);
}
~~~

A message sent to the router with the header:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-100")
    .setHeader("spring.cloud.function.definition", "priorityHandler")
    .build();
~~~

The router invokes `priorityHandler`. If the message selects `standardHandler`, the router invokes the other handler.

### 6.1. Testing Routing to a Consumer

To verify routing without relying on logs, use a thread-safe recorder:

~~~java
class RouteRecorder {
    private final BlockingQueue<String> received = new LinkedBlockingQueue<>();

    void record(String route, String value) {
        received.add(route + ":" + value);
    }

    String next() throws InterruptedException {
        return received.poll(1, TimeUnit.SECONDS);
    }
}
~~~

Test application:

~~~java
@SpringBootApplication
@EnableTestBinder
class RoutingTestApplication {

    @Bean
    RouteRecorder routeRecorder() {
        return new RouteRecorder();
    }

    @Bean
    Consumer<String> priorityHandler(RouteRecorder recorder) {
        return value -> recorder.record("priority", value);
    }

    @Bean
    Consumer<String> standardHandler(RouteRecorder recorder) {
        return value -> recorder.record("standard", value);
    }
}
~~~

Test:

~~~java
@SpringBootTest(
    classes = RoutingTestApplication.class,
    properties = "spring.cloud.stream.function.routing.enabled=true"
)
class RoutingTest {

    @Autowired
    InputDestination input;

    @Autowired
    RouteRecorder recorder;

    @Test
    void routesToFunctionNamedInHeader() throws Exception {
        Message<byte[]> message = MessageBuilder
            .withPayload("order-100".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .setHeader("spring.cloud.function.definition", "priorityHandler")
            .build();

        input.send(message, "functionRouter-in-0");

        assertThat(recorder.next()).isEqualTo("priority:order-100");
    }
}
~~~

Because the handlers are Consumers, the router creates no output binding to return messages. The recorder lets you verify exactly which handler was invoked.

### 6.2. Routing with SpEL

When selecting a handler based on a header, you can use an expression:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order-101")
    .setHeader("route", "priority")
    .setHeader(
        "spring.cloud.function.routing-expression",
        "headers['route'] == 'priority' ? 'priorityHandler' : 'standardHandler'"
    )
    .build();
~~~

SpEL receives the Message as its root object; it can access payload and headers. You should test:

- Valid header values for each branch.
- Missing or null headers.
- Unrecognized values.
- Non-existent target functions.
- Failing expressions or expressions returning invalid function names.

Do not allow untrusted clients to submit arbitrary SpEL expressions or function definitions. Use an allowlist of routes, validate inputs, and restrict which functions can be invoked.

### 6.3. MessageRoutingCallback for Complex Logic

When routing rules do not fit SpEL cleanly, provide a `MessageRoutingCallback` bean:

~~~java
@Bean
MessageRoutingCallback messageRoutingCallback() {
    return message -> {
        String eventType = (String) message.getHeaders().get("eventType");

        return switch (eventType == null ? "" : eventType) {
            case "PRIORITY_ORDER" -> "priorityHandler";
            case "STANDARD_ORDER" -> "standardHandler";
            default -> throw new IllegalArgumentException(
                "Unsupported event type: " + eventType
            );
        };
    };
}
~~~

`MessageRoutingCallback` takes `Message<?>` and returns a function definition. The callback takes precedence over headers and routing properties. When a callback exists, other `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` directives are ignored.

Unit test the callback independently by passing mock Messages and asserting the returned function name. Then use the Test Binder for integration testing to confirm the router actually invokes the right Consumer.

## 7. RoutingFunction When the Target Is a Function

When the router selects a Consumer, no output is needed because Consumers return nothing. When the router selects a Function, the Function's result can be sent to the output binding of RoutingFunction. The framework creates the output binding when needed; do not assume the router always has an output binding even when all targets are Consumers.

If you need to test routing to Functions:

1. Create two Functions with compatible input/output types.
2. Send messages to `functionRouter-in-0` with headers selecting each Function.
3. Receive results from the output binding created by the router.
4. Assert payloads and required headers.

If the Functions have different output types, verify type conversion/content types and define a clear output contract. Avoid forcing a single output binding to emit unrelated payload types without a unified schema or content type.

## 8. Routing Output with `spring.cloud.stream.sendto.destination`

Routing FROM a Consumer/Function lets a function decide the output destination via the `spring.cloud.stream.sendto.destination` header.

~~~java
record OrderEvent(String orderId, String region) {}

@Bean
Function<OrderEvent, Message<OrderEvent>> routeByRegion() {
    return event -> MessageBuilder
        .withPayload(event)
        .setHeader(
            "spring.cloud.stream.sendto.destination",
            "orders." + event.region()
        )
        .build();
}
~~~

If region is `eu`, the framework sends output to destination `orders.eu`. If destinations are known upfront, declare corresponding producer properties. If creating destinations dynamically, use `spring.cloud.stream.dynamicDestinations` to allow only a predefined list of destinations.

Do not concatenate untrusted input directly into destination names. Map business values to topic names from a controlled lookup table, such as `EU -> orders.eu`, `US -> orders.us`. This prevents senders from creating arbitrary topics.

### 8.1. Testing Dynamic Output Routing

The Test Binder can verify that the function sets the destination header properly and the message appears at the corresponding output:

~~~java
@SpringBootTest(
    classes = DestinationRoutingTest.TestApplication.class,
    properties = {
        "spring.cloud.function.definition=routeByRegion",
        "spring.cloud.stream.dynamic-destinations=orders.eu"
    }
)
class DestinationRoutingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void routesOutputToRegionDestination() {
        Message<byte[]> message = MessageBuilder
            .withPayload("eu|order-9".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        input.send(message, "routeByRegion-in-0");

        Message<byte[]> routed = output.receive(1_000, "orders.eu");
        assertThat(routed).isNotNull();
        assertThat(new String(routed.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("order-9");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {

        @Bean
        Function<String, Message<String>> routeByRegion() {
            return input -> {
                String[] parts = input.split("\\|", 2);
                String destination = switch (parts[0]) {
                    case "eu" -> "orders.eu";
                    default -> throw new IllegalArgumentException("Unknown region");
                };
                return MessageBuilder.withPayload(parts[1])
                    .setHeader("spring.cloud.stream.sendto.destination", destination)
                    .build();
            };
        }
    }
}
~~~

This test verifies route mapping inside the application and the allowlist under the Test Binder. Real-broker integration tests are still required to verify topic provisioning, publish permissions, and producer properties for dynamic destinations.

## 9. When Is StreamBridge Used?

Functions and Suppliers are the natural sources of the streaming model. However, messages can originate from a REST controller, scheduler, legacy callback, non-binder listener, or another business service. `StreamBridge` lets you send objects/Messages from those sources to an output binding.

Example publisher:

~~~java
@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
~~~

If `orders-out-0` is already declared as an output binding, StreamBridge uses that binding. You can create the binding at startup using:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orders-out-0
      bindings:
        orders-out-0:
          destination: orders.created
          content-type: application/json
~~~

`StreamBridge.send` accepts `Object`, so it can send a POJO or a `Message<?>`. Payloads go through conversion, partitioning, and producer properties just like outputs produced by a Function/Supplier.

## 10. Static Bindings vs. Dynamic Destinations with StreamBridge

Two common ways to send:

| Send Pattern | Example | Behavior |
|---|---|---|
| Declared binding | `send("orders-out-0", event)` | Uses an output binding already configured with destination and producer properties. |
| Dynamic destination | `send("orders.eu", event)` | If the binding does not exist yet, StreamBridge creates an output binding on first send and caches it for reuse. |

When using dynamic destinations:

- The destination may be auto-provisioned if supported by the binder and the account has permissions.
- Dynamic bindings are cached for reuse.
- The default cache size is 10; configurable via `spring.cloud.stream.dynamic-destination-cache-size`.
- When there are too many destinations, older bindings may be evicted and recreated.
- Dynamic bindings created by StreamBridge are not managed in the application context the same way as static bindings.

For predictable destinations, declare bindings explicitly to control partitioning, serializers, retries, DLQs, required groups, and binder-specific properties.

### 10.1. Restricting Dynamic Destinations

Configure an allowlist:

~~~yaml
spring:
  cloud:
    stream:
      dynamic-destinations:
        - orders.eu
        - orders.us
        - orders.apac
~~~

When the list is set, only destinations in the list can be dynamically bound. This is an essential safeguard when destinations are derived from request data or headers.

When using multiple binders, you can specify the binder in an overload:

~~~java
streamBridge.send("orders-out-0", "kafka", event);
~~~

Overloads supporting a binder name also have variants accepting `MimeType`. The binder name only takes effect when StreamBridge creates a dynamic binding; if the binding already exists or is declared in `spring.cloud.stream.output-bindings`, the binder name argument does not change the binder already attached to that binding.

## 11. Synchronous and Asynchronous Sending with StreamBridge

By default, StreamBridge sends on the caller thread and the send operation is blocking. Asynchronous sending can be enabled:

~~~java
streamBridge.setAsync(true);
boolean accepted = streamBridge.send("orders-out-0", event);
~~~

Async send is useful when you do not want the calling thread to block on the send operation. However, switching threads affects observability context/tracing. If trace context must be preserved, configure Micrometer context propagation per the documentation for your version.

Do not treat `send(...) == true` as end-to-end confirmation that a consumer has processed the message or the broker has persisted it durably. The boolean indicates that the send operation was accepted at the framework's channel layer. Delivery guarantees, broker acknowledgements, and transactions still depend on the binder, producer configuration, and middleware.

If the application needs to return an HTTP response, clearly define whether the API response means "request received", "placed onto channel", or "confirmed by broker". Do not advertise a stronger guarantee than what send actually provides.

## 12. Testing StreamBridge with the Test Binder

The Test Binder lets you test StreamBridge without a broker:

~~~java
@SpringBootTest(
    classes = StreamBridgeTest.TestApplication.class,
    properties = "spring.cloud.stream.dynamic-destinations=orders.eu"
)
class StreamBridgeTest {

    @Autowired
    StreamBridge streamBridge;

    @Autowired
    OutputDestination output;

    @Test
    void sendsToAllowedDynamicDestination() {
        Message<byte[]> message = MessageBuilder
            .withPayload("order-200".getBytes(StandardCharsets.UTF_8))
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.TEXT_PLAIN)
            .build();

        assertThat(streamBridge.send("orders.eu", message)).isTrue();

        Message<byte[]> received = output.receive(1_000, "orders.eu");
        assertThat(received).isNotNull();
        assertThat(new String(received.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("order-200");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class TestApplication {
    }
}
~~~

This test verifies that StreamBridge creates the dynamic binding, sends the message to the right destination, and preserves the expected payload/content type in the Test Binder environment.

You should add tests for:

- Sending to a configured static binding.
- Sending to a destination outside the allowlist and verifying the operation fails.
- Sending a POJO and verifying JSON conversion.
- Sending a Message with business headers.
- Verifying `send` returns false when the channel rejects the message under appropriate test conditions.
- Verifying destination names are produced via route mapping rather than taken directly from arbitrary input.

For logic calling StreamBridge, you can inject `StreamOperations` (the interface implemented by StreamBridge) to mock it in unit tests. This lets you assert binding names, payloads, and invocation counts without initializing a binder.

## 13. Testing Multiple Independent Functions and Multiple Outputs

When an application has multiple functions without composing them into one pipeline, declare the function list separated by `;`:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase;reverse
~~~

Each function has its own input/output bindings. Tests should send to the exact input binding and read from the exact output binding:

~~~java
input.send(message, "uppercase-in-0");
input.send(message, "reverse-in-0");

Message<byte[]> upper = output.receive(1_000, "uppercase-out-0");
Message<byte[]> reversed = output.receive(1_000, "reverse-out-0");
~~~

For functions with multiple outputs, binding names include indices such as `split-out-0` and `split-out-1`. Tests must assert both branches, message counts, and corresponding payloads; do not only read the first output and stop.

With multiple inputs, use `InputDestination.send(message, destinationName)` to feed messages into the right source. This is especially important for functions with multi-input arity, because sending data to the wrong input binding can leave the topology waiting for another input or produce unexpected results.

## 14. Testing Headers and Content Types

Routing, composition, and StreamBridge frequently rely on headers. Verify:

- Whether `MessageHeaders.CONTENT_TYPE` matches the format required by the converter.
- Whether `spring.cloud.function.definition` names the right target function.
- Whether `spring.cloud.function.routing-expression` evaluates to a valid route.
- Whether `spring.cloud.stream.sendto.destination` specifies an allowed destination.
- Whether correlation ID, trace ID, or tenant ID propagates per contract.
- Whether sensitive headers are stripped before publishing.

Do not assume all input headers automatically appear on the output. Functions returning plain payloads typically do not preserve all headers. When headers must be propagated, return `Message<?>` and copy selectively:

~~~java
@Bean
Function<Message<String>, Message<String>> enrich() {
    return input -> MessageBuilder
        .withPayload(input.getPayload().trim())
        .setHeader("correlationId", input.getHeaders().get("correlationId"))
        .setHeader("processedBy", "order-normalizer")
        .build();
}
~~~

Copy only necessary headers. Avoid forwarding tokens, credentials, or internal headers to external destinations.

## 15. The Test Binder Does Not Replace Broker Integration Tests

The Spring Integration Test Binder is an in-JVM message broker built on Spring Integration. It is well-suited for testing functions, composition, binding wiring, and basic message flows without middleware.

The Test Binder does not prove that Kafka, RabbitMQ, or Pulsar-specific features work properly. After unit tests and Test Binder tests pass, write integration tests with the real binder for the following requirements:

| Behavior | Why a Real Broker Is Needed |
|---|---|
| Topic/queue/exchange provisioning | Depends on broker permissions, topology, and configuration. |
| Partitions, routing keys, consumer groups | Distribution and ordering are determined by the binder/broker. |
| Serialization and schema registry | Depends on serializers, schemas, and broker validation. |
| Retries, acknowledgements, DLQs | Semantics differ among Kafka, RabbitMQ, and Pulsar. |
| Transactions and delivery guarantees | Depends on the specific producer, broker, and binder. |
| ACLs, authentication, TLS | Not fully emulated by an in-memory binder. |
| Dynamic destination lifecycle | Requires verifying provisioning, caching, and cleanup on a real broker. |

A practical strategy:

1. Unit tests for pure functions and route mapping.
2. Test Binder for composition, input/output bindings, routing headers, and StreamBridge.
3. Integration tests with a real broker (for example via Testcontainers) for provisioning, serialization, routing, partitioning, and delivery behavior.
4. Smoke tests in the deployment environment to verify configuration, permissions, and observability.

Note: when `spring-cloud-stream-test-binder` is on the test classpath, Spring Cloud Stream uses the Test Binder for testing. Do not mix the Test Binder and regular middleware binders in the same test module expecting one test context to use both. Separate integration tests using real Kafka/Rabbit/Pulsar binders from the test module using the in-JVM Test Binder, or configure Test Binder auto-configuration exclusions per your version's guidance.

## 16. Suggested Test Matrix

| Group | Scenario | Expected Result |
|---|---|---|
| Composition | `uppercase|addSuffix` with valid payload. | Output follows exact transformation order. |
| Composition | Input function errors. | Exception/error flow is observed properly. |
| Composition | Output type of earlier function mismatches input of next function. | Conversion succeeds or test catches type mismatch. |
| Composition | Correlation ID header. | Header is preserved/forwarded per configured contract. |
| Independent functions | `uppercase;reverse`. | Each binding receives and emits its own messages properly. |
| Routing | Header selects `priorityHandler`. | Only the priority handler is invoked. |
| Routing | Header selects `standardHandler`. | Only the standard handler is invoked. |
| Routing | Missing or invalid route. | Fails/falls back per policy; never routes arbitrarily. |
| Routing | MessageRoutingCallback exists. | Callback takes precedence over routing headers/properties. |
| Output routing | `sendto.destination=orders.eu`. | Output goes to the selected destination. |
| StreamBridge | Static binding. | Sends through the right output binding. |
| StreamBridge | Valid dynamic destination. | Binding is created and message reaches the right destination. |
| StreamBridge | Destination outside allowlist. | Does not create a binding outside the list. |
| StreamBridge | Many dynamic destinations. | Caching/eviction is understood and operates properly. |
| StreamBridge | Async send. | Caller is not blocked per config; trace context is handled. |
| Broker integration | ACLs/provisioning/partitions/schemas. | Real broker enforces configuration properly. |

## 17. Common Errors

1. Using `;` when intending to compose functions with `|`; the result is two independent functions instead of a pipeline.
2. Using the original function's binding name when testing composition; composition has its own binding name.
3. Assuming a Consumer creates an output binding; Consumers return no data to publish.
4. Sending routing messages to `uppercase-in-0` instead of `functionRouter-in-0`.
5. Assuming the `spring.cloud.function.definition` header always wins; `MessageRoutingCallback` can take higher precedence.
6. Allowing clients to send arbitrary function names or SpEL, enabling routes outside the permitted handler list.
7. Routing output using a destination taken straight from the payload without an allowlist.
8. Confusing `sendto.destination` with `StreamBridge.send` binding names; they are two different output routing mechanisms.
9. Calling `StreamBridge.send` with a physical destination name while configuring a static binding under a different binding name.
10. Thinking `send() == true` means the broker persisted the message or a consumer processed it.
11. Creating too many dynamic destinations without bounding the allowlist/cache.
12. Using the Test Binder to conclude that real broker partitions, retries, DLQs, or transactions work properly.
13. Assuming input headers are always propagated to a function's output.
14. Testing multiple inputs/outputs without specifying binding names, causing messages to be sent to or read from the wrong destination.

## 18. Implementation and Testing Workflow

1. Write small functions and unit test their business logic.
2. Declare composition via `spring.cloud.function.definition` and verify binding names.
3. Use the Test Binder to send inputs to the right bindings and assert outputs.
4. If handler routing is needed, enable RoutingFunction and define the route contract.
5. Validate routes with an allowlist or MessageRoutingCallback; test both valid and invalid routes.
6. If routing output dynamically, use `sendto.destination` or StreamBridge and restrict allowed destinations.
7. Test StreamBridge with static bindings first, then test dynamic destinations and cache behavior.
8. Verify content types, payloads, keys, correlation IDs, and required headers.
9. Write integration tests with the right Kafka/RabbitMQ/Pulsar binder for provisioning, partitioning, serialization, security, and delivery semantics.
10. Monitor logs, metrics, and traces to see which route was chosen, where messages were sent, and at which boundary errors occurred.

Function composition breaks logic into small, independently testable steps; routing decides handlers or destinations based on messages; StreamBridge feeds data from external sources into the same Spring Cloud Stream binding mechanism. By testing in layers and verifying the broker in integration tests, applications can evolve pipelines or destinations while preserving clear message contracts.

## References

- [Spring Cloud Stream 5.1 – Testing with Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream – Event Routing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html)
- [Spring Cloud Stream – Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Function 4.0 – Function Composition and Routing](https://docs.spring.io/spring-cloud-function/docs/current/reference/html/spring-cloud-function.html)
