# Supplier<T>: Generating Data Without Input

In Spring Cloud Function, **Supplier<T>** describes a source that generates or provides data. Whenever the source is triggered, the application calls the **get()** method to obtain a value of type **T**. The function accepts no business arguments from the caller, so the same logic can be triggered via HTTP, an event publishing schedule, or a serverless environment through an appropriate adapter.

This lesson belongs to the **Function Model** chapter of **SPRING_CLOUD_FUNCTION**. The focus is on how to design, register, execute, and test a Supplier independently of the invocation protocol; then connect that data source with FunctionCatalog, composition, messages, and deployment mechanisms.

## 1. What is Supplier<T>?

**java.util.function.Supplier<T>** is a functional interface with a single abstract method:

~~~java
@FunctionalInterface
public interface Supplier<T> {
    T get();
}
~~~

- **No input parameters:** the call is **get()**, not **apply(input)**.
- **A result of type T:** such as a String, a Java object, a Message<T>, or a reactive publisher like Flux<T>.
- **Can be called multiple times:** each invocation can generate a new result or re-read current data, depending on the implementation.
- **Does not mean having no dependencies:** a Supplier can still use a Clock, repository, configuration, or service to compute the result. What does not exist is *a business argument passed into get()*.

Plain Java example:

~~~java
Supplier<String> greeting = () -> "Hello Spring Cloud Function";

String first = greeting.get();
String second = greeting.get();
~~~

In this example, **get()** returns the same string. For a Supplier that generates timestamps, identifiers, or system state snapshots, two calls may return different data.

| Function Model | Signature | Primary Role | Example |
| --- | --- | --- | --- |
| **Supplier<T>** | () → T | Generate or provide data | Generate periodic heartbeats |
| **Function<I, O>** | I → O | Transform input data | Convert an order into an invoice |
| **Consumer<T>** | T → void | Receive and process data | Write an event to a storage system |

A request that needs the request content, such as looking up an order by a client-supplied ID, is usually better suited to **Function<Request, Response>**. Supplier is suitable when the source itself knows what data to generate or fetch.

## 2. How Does Supplier Operate in Spring Cloud Function?

Spring Cloud Function detects functional beans of types **Supplier**, **Function**, and **Consumer**, and registers them into **FunctionCatalog**. The catalog provides a way to look up and compose functions by name, allowing adapters to invoke the right business logic.

~~~mermaid
flowchart LR
    A["HTTP GET"] --> B["HTTP adapter"]
    C["Poller schedule"] --> D["Stream adapter"]
    E["Serverless trigger"] --> F["Serverless adapter"]
    B --> G["FunctionCatalog: heartbeat"]
    D --> G
    F --> G
    G --> H["Supplier.get()"]
    H --> I["Heartbeat"]
~~~

The diagram illustrates **a single function contract** with different trigger mechanisms; it does not imply that merely creating one bean makes all three protocols work automatically. Each environment requires its corresponding dependencies, configuration, and adapter.

Basic lifecycle:

1. Spring instantiates the Supplier bean in the application context.
2. Spring Cloud Function registers the bean under a function name, for example **heartbeat**.
3. The adapter receives a trigger signal: a GET request, a poll cycle, or an invocation from a serverless runtime.
4. The adapter retrieves the function from the catalog, invokes **get()**, and processes the return value according to the target protocol.

**Distinguish bean instantiation time from data generation time:** declaring a Supplier bean does not mean data is already generated at application startup. With a lambda **() -> createData()**, the body typically runs only when **get()** is called.

## 3. Complete Example: Emitting a Heartbeat for a Service

Suppose a warehouse system wants to provide a message indicating the service name and the timestamp when the signal is emitted. The message generation logic does not need a request body or an input event.

In a Spring Boot project already managing compatible Spring Cloud versions, add the starter for the HTTP adapter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-function-web</artifactId>
</dependency>
~~~

Declare the application and the **heartbeat** bean:

~~~java
package example.function;

import java.time.Clock;
import java.time.Instant;
import java.util.function.Supplier;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class FunctionApp {

    public static void main(String[] args) {
        SpringApplication.run(FunctionApp.class, args);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    Supplier<Heartbeat> heartbeat(Clock clock) {
        return () -> new Heartbeat("warehouse", Instant.now(clock));
    }

    public record Heartbeat(String service, Instant createdAt) {}
}
~~~

Here:

- The bean method name **heartbeat** is the function name recognized by Spring Cloud Function.
- **Heartbeat** is structured output data; the HTTP adapter can serialize it into JSON.
- **Clock** is injected via dependency injection to decouple time retrieval from the function logic and facilitate testing.
- **Instant.now(clock)** is *inside* the lambda. Each time **get()** runs, a new heartbeat is created with the invocation timestamp.

When the application uses the web adapter and runs on the default port 8080, you can test it with:

~~~bash
curl -i http://localhost:8080/heartbeat
~~~

Example response body:

~~~json
{
  "service": "warehouse",
  "createdAt": "2026-01-15T08:30:00Z"
}
~~~

The timestamp in the JSON is only an illustrative value; the actual result depends on the invocation time. Since Supplier has no parameters, the request body is not input data for **get()**. GET-style endpoints should be used for safe observation/data-provision operations, avoiding side-effecting actions such as charging money or creating orders.

## 4. Generating Data per Call vs. Capturing Once

The following two implementations have very different meanings.

**Error-prone approach:** the timestamp is captured when Spring creates the bean, so subsequent calls all return a stale message.

~~~java
@Bean
Supplier<Heartbeat> staleHeartbeat(Clock clock) {
    Heartbeat snapshot = new Heartbeat("warehouse", Instant.now(clock));
    return () -> snapshot;
}
~~~

**Suitable approach when fresh data is needed:** generate the data inside the function body.

~~~java
@Bean
Supplier<Heartbeat> freshHeartbeat(Clock clock) {
    return () -> new Heartbeat("warehouse", Instant.now(clock));
}
~~~

Returning a fixed object is not always wrong: a Supplier providing immutable configuration may intentionally reuse the result. You need to clearly determine requirements for data freshness, query cost, caching, and the impact of each call.

## 5. FunctionCatalog and Composition

FunctionCatalog is the lookup layer for functional beans managed by Spring Cloud Function. Thanks to the catalog, callers over HTTP or event binders can look up functions by name instead of depending directly on implementation classes.

A Supplier can also serve as the input to a transformation chain. For example, adding a **describeHeartbeat** bean to the configuration class above:

~~~java
@Bean
java.util.function.Function<Heartbeat, String> describeHeartbeat() {
    return heartbeat ->
        heartbeat.service() + " | " + heartbeat.createdAt();
}
~~~

The chain has the form:

~~~text
Supplier<Heartbeat> heartbeat
    -> Function<Heartbeat, String> describeHeartbeat
    -> String result
~~~

You can select a composed function definition in the Spring Cloud Function configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat|describeHeartbeat
~~~

The **|** symbol expresses the composition order: invoke the Supplier first to obtain **Heartbeat**, then pass that result into the Function. The final result has type **String**. In an application containing multiple functions, explicitly selecting a definition helps the adapter know which function or function chain to expose/bind. The exact path and invocation mechanism are determined by the adapter.

**Type composition rule:** the Supplier's output **T** must be compatible with the input of the Function following it. You cannot directly compose **Supplier<Heartbeat>** with **Function<Order, Invoice>** without an appropriate conversion step.

## 6. Using the Same Supplier to Emit Events

In an event-driven model, a Supplier typically plays the role of **an outbound data source**. When using Spring Cloud Stream with an appropriate binder (such as Kafka or RabbitMQ), a synchronous Supplier can be polled by the framework to send each value to a destination.

Illustrative configuration example for an application selecting only the **heartbeat** function to emit events:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat
    stream:
      bindings:
        heartbeat-out-0:
          destination: heartbeat-events
      poller:
        fixed-delay: 5000
~~~

Meaning:

- **heartbeat-out-0** is the output binding name of the **heartbeat** Supplier.
- **destination** is the logical target; the broker and binder determine the actual mapping.
- **fixed-delay: 5000** configures the poller delay interval in milliseconds; it should not be interpreted as a guarantee of delivering events at exact 5-second intervals.
- Each eligible poll can trigger **get()**, after which the framework sends the data to the destination.

The configuration above takes effect only when the application has Spring Cloud Stream, a binder, a broker, and the required connection properties. If the goal is **processing incoming events**, use **Consumer<T>** or **Function<I, O>** instead of trying to read input events via a Supplier.

In a serverless environment, the same **Supplier<Heartbeat>** logic can be packaged using an adapter suited to the platform. Triggers, handler configuration, data conversion rules, and execution lifecycle depend on the runtime; the Supplier itself does not create trigger schedules or connect to cloud services.

## 7. Supplier and Messages with Metadata

When metadata describing an event needs to be included, a Supplier can return **Message<T>** instead of just **T**. Example using Spring Messaging:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Supplier<Message<Heartbeat>> heartbeatMessage(Clock clock) {
    return () -> MessageBuilder
        .withPayload(new Heartbeat("warehouse", Instant.now(clock)))
        .setHeader("eventType", "HEARTBEAT")
        .build();
}
~~~

In this example, **payload** is the business data, while **eventType** is a header. The adapter/binder decides how headers map to the transport protocol. You should not assume every header type is preserved across all systems.

Spring Cloud Function supports type conversion at the boundary of many adapters. For example, the HTTP adapter can convert **Heartbeat** to JSON, while the event binder encodes the payload into a message sent through the broker. The Supplier does not have to write serialization logic for each protocol.

## 8. Synchronous Supplier and Reactive Supplier

A **regular Supplier<T>** returns one result when **get()** is called. With a polling mechanism, the framework can call it repeatedly to obtain consecutive results.

A **reactive Supplier<Flux<T>>** returns a publisher capable of emitting multiple elements over time. Example with Project Reactor:

~~~java
import java.time.Duration;
import reactor.core.publisher.Flux;

@Bean
Supplier<Flux<Heartbeat>> reactiveHeartbeat(Clock clock) {
    return () -> Flux.interval(Duration.ofSeconds(5))
        .map(index -> new Heartbeat("warehouse", Instant.now(clock)));
}
~~~

In reactive stream integration, the framework typically obtains the publisher from the Supplier and subscribes to the element stream; emission timing is controlled by the publisher instead of calling **get()** for each event. Verify the behavior of the adapter and library version in use; not every HTTP endpoint automatically becomes a continuous data stream.

| Criterion | Supplier<Heartbeat> | Supplier<Flux<Heartbeat>> |
| --- | --- | --- |
| Result of a single **get()** call | One Heartbeat | One publisher |
| Source of subsequent elements | Repeated **get()** calls or poller | Flux stream after subscription |
| Best suited for | Reading instantaneous state, scheduled single-message emission | Continuous data sources with reactive processing |
| Things to note | Poll rate, latency of **get()** | Subscription, backpressure, stream cancellation, and resources |

Do not expose an infinite source over regular synchronous HTTP without explicitly designing streaming responses, timeouts, and connection-closing mechanisms.

## 9. Testing Supplier Independently of Adapters

A practical benefit of the functional model is that you can test the **get()** logic itself without starting a web server, broker, or serverless environment.

JUnit 5 example for the **heartbeat** bean:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;

class FunctionAppTest {

    @Test
    void heartbeatUsesProvidedClock() {
        Instant fixedTime = Instant.parse("2026-01-15T08:30:00Z");
        Clock fixedClock = Clock.fixed(fixedTime, ZoneOffset.UTC);

        Supplier<FunctionApp.Heartbeat> supplier =
            new FunctionApp().heartbeat(fixedClock);

        FunctionApp.Heartbeat result = supplier.get();

        assertEquals("warehouse", result.service());
        assertEquals(fixedTime, result.createdAt());
    }
}
~~~

The test verifies that the Supplier produces a result with the expected structure and respects the provided Clock. Separate integration tests should verify HTTP routes, event bindings, or serverless adapters when those components are actually used.

## 10. Common Design Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Timestamp or data is always stale | Data is created outside the lambda during bean initialization | Move data generation into **get()** if fresh values are required |
| Supplier is not exposed or bound properly | Missing adapter, multiple beans without a selected function definition, or wrong binding config | Check dependencies, bean names, and **spring.cloud.function.definition** |
| Events emitted unexpectedly fast or slow | Misunderstanding poller mechanism or reactive streams | Configure poll schedule, observe actual rate, and apply appropriate limits |
| HTTP GET causes business state changes | Placing order creation, payment, or state writes inside **get()** | Use an API/function with inputs and appropriate HTTP semantics |
| Incorrect results under concurrent calls | Supplier holds shared mutable state without synchronized access | Prefer immutability, avoid shared state, or synchronize properly |
| Single invocation is slow or hangs | **get()** performs long blocking I/O or calls an external service without timeout | Set timeouts, monitor latency, consider caching or async architecture |

Also note that an event-producing Supplier may be triggered again after failures or application restarts. If the result has business effects on the receiving system, design event identifiers, consumer-side idempotency, and delivery strategies at the integration layer.

## 11. Practice Exercises

**Exercise 1 — Simple Supplier:** create a **Supplier<HealthSnapshot>** bean with two fields **service** and **capturedAt**; use **Clock** so time is testable. Call **get()** in a unit test and assert that the service name is correct.

**Exercise 2 — Composition:** write a **Function<HealthSnapshot, String>** to output a summary string, then configure the chain **healthSnapshot|formatHealthSnapshot**. Explain why the Function must accept the exact type returned by the Supplier.

**Exercise 3 — Choosing the trigger mechanism:** for the three needs *reading status when a user opens a page*, *emitting heartbeats to a broker on a schedule*, and *consuming commands from Kafka*, choose respectively an HTTP Supplier, a Stream Supplier, and a Consumer/Function accepting input. Identify the adapter component required for each case.

### Key Takeaways

- **Supplier<T>** represents a **() → T** function, obtaining data without receiving business arguments from the caller.
- **@Bean Supplier<T>** is registered by Spring Cloud Function and looked up via **FunctionCatalog**; suitable adapters can trigger the same logic.
- For dynamic data, place the generation logic inside **get()** and control dependencies such as time, I/O, and shared state.
- A Supplier can be composed with **Function<T, R>**, return **Message<T>**, or return a reactive publisher, though triggering and data conversion depend on the deployment environment.
