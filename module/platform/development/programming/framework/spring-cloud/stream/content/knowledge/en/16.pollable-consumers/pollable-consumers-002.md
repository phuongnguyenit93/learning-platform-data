# Declaring pollable-source and Creating PollableMessageSource

Spring Cloud Stream typically consumes messages using an event-driven model: the binder receives a message from the broker and immediately invokes a Consumer or Function when the message arrives. In some applications, code needs to proactively decide when to fetch messages, how many messages to retrieve within a given period, or only read when the system has enough processing resources. Pollable consumers address this need with PollableMessageSource.

To create a pollable input binding in the functional model, declare the spring.cloud.stream.pollable-source property. Spring Cloud Stream creates the corresponding input binding and provides an implementation of PollableMessageSource for the application to call poll(...). The application manages the polling schedule using @Scheduled, TaskScheduler, or a controlled loop. PollableMessageSource is not an object that you instantiate yourself with new; the binder creates it and connects it to the configured destination.

## 1. When Should You Use a Pollable Consumer?

A pollable consumer is suitable when the application needs to control the message retrieval pace:

- Read only when a local resource still has processing capacity, such as worker slots or a connection pool.
- Limit the number of messages fetched in each cycle to avoid overloading a database or downstream service.
- Integrate with an application's custom scheduler or orchestrator.
- Proactively handle each message and decide how to acknowledge, reject, or return the message to the broker.

The standard message-driven model is more suitable when the application can process messages as soon as the broker delivers them and does not need application-layer polling control. Polling adds responsibility for scheduling, retrieval pacing, error handling, and acknowledgment to application code. Choose a pollable consumer only when that control delivers concrete benefits.

## 2. Declaring pollable-source

Suppose an application needs to proactively read order events from the orders.created destination. Configuration:

~~~yaml
spring:
  cloud:
    stream:
      pollable-source: orders
      bindings:
        orders-in-0:
          destination: orders.created
          group: order-poller
          content-type: application/json
~~~

The spring.cloud.stream.pollable-source property takes the logical name of the pollable source. With the value orders, Spring Cloud Stream creates a binding named orders-in-0, following the functional model's binding convention. That binding points to the orders.created destination and the order-poller consumer group.

Distinguish the three names in the configuration:

| Value | Role |
|---|---|
| orders | The pollable source name declared in spring.cloud.stream.pollable-source |
| orders-in-0 | The input binding name used by the application for configuration |
| orders.created | The physical destination on the broker, such as a Kafka topic or corresponding binder resource |

Multiple pollable sources can be declared as a semicolon-separated list, for example orders;payments. Each name creates a corresponding input binding following the convention, such as orders-in-0 and payments-in-0. When multiple sources exist, verify the wiring so each poller receives its intended source.

Do not declare spring.cloud.function.definition solely to create this pollable source. A pollable consumer uses PollableMessageSource directly and does not need a Consumer bean for the framework to invoke automatically on events.

## 3. How Is PollableMessageSource Created and Injected?

Once the binding is created from the configuration, the binder provides PollableMessageSource. With a single pollable source in the application, it can be injected directly by type:

~~~java
import org.springframework.cloud.stream.binder.PollableMessageSource;
import org.springframework.stereotype.Component;

@Component
public class OrderPoller {
    private final PollableMessageSource source;

    public OrderPoller(PollableMessageSource source) {
        this.source = source;
    }
}
~~~

The application does not write its own implementation, does not manually open a connection to Kafka/RabbitMQ/Pulsar in this class, and does not need to declare a @Bean PollableMessageSource. The binder handles the connection and provides the abstraction for the application to call poll.

If the application has multiple pollable sources, you must distinguish each binding when injecting so pollers do not read from the wrong destination. Binding names and registered qualifiers may depend on the version/framework configuration; inspect bean wiring in the application context and test each source individually.

## 4. Calling poll and Processing a Message

PollableMessageSource provides the method:

~~~java
boolean poll(MessageHandler handler);
~~~

MessageHandler receives a Spring Message. A return value of true indicates a message was received and processed successfully; false indicates no message was retrieved for processing in that poll. The callback is invoked synchronously during the poll call.

Example of processing a message:

~~~java
source.poll(message -> {
    OrderCreated event = (OrderCreated) message.getPayload();
    orderService.process(event);
});
~~~

Inside the callback, the application reads the payload and invokes business logic. When the callback completes normally, the poll is considered successful and the default acknowledgment mechanism acknowledges the message according to the binder. If the callback throws an exception, the error is routed through the pollable source's error channel mechanism; how the broker rejects or redelivers depends on the binder and error configuration.

### Data Type Hint for Payload Conversion

There is an overload that accepts a ParameterizedTypeReference:

~~~java
boolean poll(MessageHandler handler, ParameterizedTypeReference<?> type);
~~~

The type parameter is a conversion hint so the message converter can convert the payload to the desired Java type. For example:

~~~java
source.poll(message -> {
    OrderCreated event = (OrderCreated) message.getPayload();
    orderService.process(event);
}, new ParameterizedTypeReference<OrderCreated>() {});
~~~

For payloads with nested generics, ParameterizedTypeReference preserves full type information:

~~~java
source.poll(message -> {
    Map<String, OrderLine> lines =
        (Map<String, OrderLine>) message.getPayload();
    orderService.processLines(lines);
}, new ParameterizedTypeReference<Map<String, OrderLine>>() {});
~~~

Ensure the binding's content-type and the message format emitted by the producer are compatible with the converter. If the consumer receives raw data or uses the binder's native deserializer, the conversion hint does not replace native serializer/deserializer configuration.

## 5. Scheduling Polling with @Scheduled

Do not call poll in a tight loop with no wait interval, because when the broker has no messages, the application will continuously query the broker and consume CPU. A common Spring integration approach is using @Scheduled:

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.cloud.stream.binder.PollableMessageSource;

@Component
public class OrderPoller {
    private final PollableMessageSource source;
    private final OrderService orderService;

    public OrderPoller(
            PollableMessageSource source,
            OrderService orderService) {
        this.source = source;
        this.orderService = orderService;
    }

    @Scheduled(fixedDelay = 500)
    public void pollOne() {
        source.poll(message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            orderService.process(event);
        }, new ParameterizedTypeReference<OrderCreated>() {});
    }
}
~~~

Enable scheduling in the application:

~~~java
@SpringBootApplication
@EnableScheduling
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

fixedDelay measures the wait time after the previous execution finishes. If processing a message takes 200 ms and the delay is 500 ms, the next poll starts roughly 500 ms after the previous one ended. When a poll has no message, the scheduler still waits until the next cycle, avoiding a busy loop.

In the example, each run calls poll only once, so at most one message is processed per cycle. This is a simple way to throttle consumption rate. If higher throughput is needed, you can call poll multiple times in one scheduler pass, but you must cap the message count or processing duration.

## 6. Fetching Multiple Messages in a Bounded Cycle

A poller can keep calling poll while messages remain, but you should set a cap so a single run does not occupy the scheduler indefinitely:

~~~java
@Scheduled(fixedDelay = 500)
public void pollBatch() {
    int processed = 0;
    int maxMessages = 20;

    while (processed < maxMessages) {
        boolean received = source.poll(message -> {
            OrderCreated event = (OrderCreated) message.getPayload();
            orderService.process(event);
        }, new ParameterizedTypeReference<OrderCreated>() {});

        if (!received) {
            break;
        }
        processed++;
    }
}
~~~

The maxMessages limit balances throughput and fairness with other scheduled tasks. If processing a single message takes a long time, consider also bounding the total duration of a polling pass. Do not run an unbounded loop when messages are always available, as the scheduler may never finish the current pass.

With a message-driven consumer, the binder actively pushes messages to the handler. With a pollable consumer, the application decides when to call poll. That is the main difference in control; it does not mean the pollable source automatically guarantees backpressure or protects all downstream resources.

## 7. Using ApplicationRunner Instead of a Scheduler

ApplicationRunner can be used to start an application-managed polling task. If you choose this approach, the runner should submit the work to a Spring-managed executor with a proper lifecycle and return; do not run an infinite polling loop directly on the ApplicationRunner thread because it will delay startup completion.

The loop on the executor must stop on application shutdown, respect interrupts, wait when a poll yields no message, and bound the number of messages per pass. You also need to log errors so an exception does not silently terminate the polling task. For most applications, @Scheduled or TaskScheduler is easier to integrate, observe, and lifecycle-manage than a hand-written loop.

## 8. Default Acknowledgment and Asynchronous Processing

Normally, poll acknowledges the message when MessageHandler completes normally. If the callback completes abnormally, the message is rejected by default; the message is not necessarily returned to the queue. Redelivery and requeue behavior depend on the binder, broker, and error-handling configuration.

If the callback only performs synchronous processing:

~~~java
source.poll(message -> {
    OrderCreated event = (OrderCreated) message.getPayload();
    orderService.process(event); // Returns only after business processing is complete
});
~~~

then default acknowledgment is tied to when the callback finishes. Do not offload work to another thread and return from the callback immediately before that work completes; the message may be acknowledged before the business logic actually succeeds.

If you need to hand off a message to another thread or process asynchronously, the application can manage acknowledgment manually via the callback in the message header:

~~~java
source.poll(message -> {
    AcknowledgmentCallback acknowledgment =
        StaticMessageHeaderAccessor.getAcknowledgmentCallback(message);

    acknowledgment.noAutoAck();

    executor.execute(() -> {
        try {
            orderService.process((OrderCreated) message.getPayload());
            acknowledgment.acknowledge(AcknowledgmentCallback.Status.ACCEPT);
        }
        catch (Exception ex) {
            acknowledgment.acknowledge(AcknowledgmentCallback.Status.REQUEUE);
        }
    });
});
~~~

This is an illustrative pattern for binders that support the corresponding acknowledgment callback. Once auto-ack is disabled, the application must ack or nack/requeue after processing; forgetting to do so can hold onto delivery resources and stall message progress. Verify the semantics of ACCEPT, REJECT, and REQUEUE for your specific binder. With Kafka, offsets track log progress; requeuing an older message can cause subsequently acknowledged messages to be redelivered depending on how the binder manages offsets.

Do not use manual acknowledgment if simple synchronous processing already meets your requirements. It increases complexity and requires handling application shutdown while work is in flight.

## 9. Error Channel and RequeueCurrentMessageException

A pollable source has a default error channel. If the callback throws an exception, an ErrorMessage is sent to an error channel named in the form &lt;destination&gt;.&lt;group&gt;.errors; this error channel is also bridged to the Spring Integration errorChannel.

You can register a @ServiceActivator to handle errors:

~~~java
@ServiceActivator(inputChannel = "orders.created.order-poller.errors")
public void handlePollingError(ErrorMessage errorMessage) {
    Throwable cause = errorMessage.getPayload();
    log.error("Cannot process a polled order message", cause);
}
~~~

The example channel name is based on the orders.created destination and order-poller group; verify the actual error channel name created by the binder. If there is no subscriber for the error channel, the error is logged by default and the message may be acknowledged as successfully processed. Therefore, do not assume that merely throwing an exception will cause the broker to redeliver automatically.

If the error handler throws RequeueCurrentMessageException, the message is returned to the broker so a subsequent poll can retrieve it again. The listener can also throw this exception directly to request a requeue and bypass the error channel according to the documented mechanism. Only requeue recoverable errors; a malformed schema or invalid business data can create a continuous redelivery loop. For unprocessable errors, use bounded retries, a DLQ, or a parking-lot flow supported by the binder.

## 10. Pollable Consumers and Binder Configuration

PollableMessageSource is a common abstraction, but how a binder performs polling and acknowledgment depends on the broker:

| Binder | Things to Note |
|---|---|
| Kafka | Polling fetches records from the consumer; offset/acknowledgment relates to record order within a partition and offset commits. Requeuing a record can affect redelivery of subsequent already-processed records. |
| RabbitMQ | Polling fetches messages from a queue; ack, reject, and requeue tie to AMQP delivery. Check prefetch, dead-letter exchange, and Rabbit binder retry settings. |
| Pulsar | Polling fetches messages from a subscription; acknowledgment and redelivery depend on subscription, acknowledgment timeout, and client/binder configuration. |

Do not assume a requeue command or acknowledgment status behaves identically across all brokers. Test with the actual binder before relying on that behavior in a business workflow.

Binding properties such as destination, group, content-type, consumer.concurrency, and extended binder properties still apply. However, PollableMessageSource exists for the application to call poll; do not confuse it with Supplier poller configuration.

## 11. Distinguishing PollableMessageSource from Supplier Pollers

Both concepts include the word poll, but they operate in opposite directions:

| Mechanism | Behavior |
|---|---|
| PollableMessageSource | The application proactively fetches messages from an input destination using source.poll(...) |
| Supplier Poller | The framework periodically invokes Supplier.get() to retrieve data and send it to an output binding |

The spring.integration.poller.fixed-delay, max-messages-per-poll, and initial-delay properties control the default poller used to trigger a Supplier. They do not automatically schedule calls to PollableMessageSource.poll(). For a pollable consumer, the application sets up its own schedule using @Scheduled, TaskScheduler, or a custom orchestration mechanism.

## 12. Testing a Pollable Source

Testing should cover both bindings and polling behavior:

- Start the application context with spring.cloud.stream.pollable-source and verify the &lt;name&gt;-in-0 binding is created.
- Verify the binding points to the expected destination and group.
- Send a valid message and call poll; verify the callback receives the expected payload.
- Call poll when no messages are available and verify it returns false.
- Use ParameterizedTypeReference to verify DTO or generic payload conversion.
- Have the callback throw an exception and verify the error channel receives the error.
- Test requeue, reject, and acknowledgment with a real binder/broker.
- Verify the scheduler does not poll too aggressively when the destination is empty.
- Test shutdown while the poller is running or a callback is processing.

The Test Binder can help verify message logic and bindings within application scope. It does not replace integration tests with Kafka, RabbitMQ, or Pulsar when verifying offset commits, ack/requeue, redelivery, DLQs, and real polling limits.

## 13. Implementation Checklist

- [ ] Declared spring.cloud.stream.pollable-source with a clear source name.
- [ ] Configured the &lt;source-name&gt;-in-0 binding pointing to the correct destination.
- [ ] Configured a stable group if the application requires a named consumer group/subscription.
- [ ] Injected the binder-provided PollableMessageSource; did not create a custom implementation.
- [ ] Selected @Scheduled, TaskScheduler, or a controlled loop.
- [ ] Handled the case where poll() returns false without busy-looping.
- [ ] Selected appropriate conversion types; used ParameterizedTypeReference when needed.
- [ ] Callback returns only after synchronous processing completes, or manual acknowledgment is properly managed.
- [ ] Error channel, retry, reject, requeue, and DLQ policies are clearly defined.
- [ ] Tested with the production binder/broker and verified shutdown behavior.

spring.cloud.stream.pollable-source creates the input binding for a pollable consumer, while PollableMessageSource is the abstraction the application uses to fetch messages at its own pace. When you configure the binding properly, inject the binder-provided source, schedule bounded polling, and understand acknowledgment/error channels, your application can control consumption rate while maintaining an observable and testable message delivery pipeline.

## References

- [Spring Cloud Stream — Producing and Consuming Messages: Using Polled Consumers](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html#using-polled-consumers)
- [Spring Cloud Stream API — PollableMessageSource](https://docs.spring.io/spring-cloud-stream/docs/current/api/org/springframework/cloud/stream/binder/PollableMessageSource.html)
