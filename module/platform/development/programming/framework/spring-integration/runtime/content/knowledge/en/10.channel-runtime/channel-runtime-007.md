# PriorityChannel and Comparator

In Spring Integration Runtime, `PriorityChannel` is a queue-backed channel used to select the next message by priority level. A `Comparator` determines the order in which messages are dequeued. These two components are useful when an `IntegrationFlow` must process urgent requests before regular ones, though they only coordinate ordering inside the channel's queue; they do not spawn workers on their own, do not preempt an already-running handler, and do not guarantee that messages finish processing in the exact order they were dequeued.

## Where Does PriorityChannel Sit in a Message Flow?

`PriorityChannel` implements `PollableChannel`. A producer sends a message into the channel; a polling consumer calls `receive` via a poller to retrieve a message; then the endpoint passes the message to the handler. The channel does not initiate execution threads on its own.

~~~mermaid
flowchart LR
    P["Producer"] -->|"send(Message)"| Q["PriorityChannel"]
    Q -->|"poll / receive"| C["Polling consumer"]
    C --> H["Service Activator or handler"]
~~~

Unlike `DirectChannel`, sending to `PriorityChannel` normally only places the message in the queue. The producer does not wait for the handler to finish. The consumer pulls messages in the order determined by the comparator, so both polling cadence and consumer count affect runtime behavior.

## Default Priority Rules

`PriorityChannel`'s default comparator reads the message's priority header. Higher priority values are dequeued first; messages without this header are treated as having priority `0`. For example, if the queue contains messages with priorities `0`, `5`, and `10`, the consumer receives priority `10` first, followed by `5` and `0`.

You can build messages using `IntegrationMessageHeaderAccessor.PRIORITY`:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PriorityChannel channel = new PriorityChannel();

Message<String> normal = MessageBuilder.withPayload("normal")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 0)
        .build();

Message<String> urgent = MessageBuilder.withPayload("urgent")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 10)
        .build();

channel.send(normal);
channel.send(urgent);

Message<?> first = channel.receive(0);
// first.getPayload() is "urgent"
~~~

`receive(0)` attempts to take a message immediately and returns `null` if the queue is empty. In real applications, polling consumers typically call `receive` on a poller schedule rather than calling `receive` directly in business code.

When custom rules are not needed, using the default `PriorityChannel` means producers only need to attach the priority header. Standardize the scale across the entire flow—for example, `0` for normal, `5` for elevated attention, and `10` for urgent. Avoid letting different producers interpret the same numeric value differently.

## Customizing with a Comparator

When additional criteria are needed, pass a `Comparator<Message<?>>` to the constructor. The example below orders by descending priority, then ascending `enqueueSequence`. The secondary criterion preserves FIFO ordering among messages of equal priority, provided the producer assigns sequence numbers from a shared counter within the scope where ordering must hold.

~~~java
import java.util.Comparator;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

@Bean
PriorityChannel priorityChannel() {
    Comparator<Message<?>> comparator =
            Comparator.<Message<?>>comparingInt(message -> {
                Integer priority = message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.PRIORITY, Integer.class);
                return priority != null ? priority : 0;
            }).reversed()
              .thenComparingLong(message -> {
                  Long sequence = message.getHeaders().get(
                          "enqueueSequence", Long.class);
                  return sequence != null ? sequence : Long.MAX_VALUE;
              });

    return new PriorityChannel(comparator);
}
~~~

Producers must attach both headers following the same convention:

~~~java
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityPublisher {

    private final PriorityChannel channel;
    private final AtomicLong sequence = new AtomicLong();

    PriorityPublisher(PriorityChannel channel) {
        this.channel = channel;
    }

    public void publish(String payload, int priority) {
        Message<String> message = MessageBuilder.withPayload(payload)
                .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("enqueueSequence", sequence.incrementAndGet())
                .build();

        if (!channel.send(message)) {
            throw new IllegalStateException("Failed to send message to PriorityChannel");
        }
    }
}
~~~

The `AtomicLong` counter in this example only orders messages within a single publisher instance. If multiple instances write to the channel or sequences originate across multiple nodes, use an appropriately scoped sequence source, or accept that FIFO holds only within each source. If `enqueueSequence` is absent, the comparator returns `Long.MAX_VALUE` for the tie-breaker; messages with the same priority and same tie-breaker value have no FIFO guarantee.

You can replace the secondary criterion with deadline, work type, or customer tier. The comparator should read immutable headers attached before sending the message. Avoid database queries, parsing large payloads, or reading state that can change while the message sits in the queue. A comparator must establish a consistent, transitive ordering and return the same result whenever comparing the same pair of messages. If comparison results shift over time, the heap structure can become misordered.

## Connecting a Polling Consumer and IntegrationFlow

Because `PriorityChannel` is a `PollableChannel`, the consumer needs a poller. You can declare the endpoint using an annotation:

~~~java
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
class PriorityHandler {

    @ServiceActivator(
            inputChannel = "priorityChannel",
            poller = @Poller(fixedDelay = "100")
    )
    public void handle(Message<?> message) {
        // Process the message payload and headers.
    }
}
~~~

In this configuration, the endpoint polls the channel with a 100 ms fixed delay. The poller controls the polling cadence; the comparator only decides which message stands at the head of the queue at `receive` time. When using Java DSL, configure the poller on the endpoint reading from the pollable channel using the API of your Spring Integration version. Do not confuse a poller with an executor: the poller schedules message retrieval, whereas an executor (if configured on the endpoint or downstream component) determines where and with what concurrency the work runs.

## Limits You Need to Understand Clearly

- **No preemption:** if a consumer has already dequeued a low-priority message and the handler is running, a newly arrived high-priority message cannot interrupt that handler. The new message will simply be prioritized on the next dequeue.
- **Dequeue order differs from completion order:** with multiple consumers or asynchronous processing, a high-priority message may be dequeued first yet finish after another message. If strict completion order is required, limit concurrency or design a dedicated serialization step.
- **No default FIFO on ties:** a priority queue does not promise arrival-order FIFO for elements whose comparison returns `0`. Add a sequence header if tie-break ordering is a business requirement.
- **Possible starvation:** a continuous stream of high-priority messages can keep low-priority messages waiting indefinitely. If fairness is needed, consider partitioning priority classes, rate-limiting, or designing a scheduler with weighted fairness.
- **No global ordering:** the comparator only orders messages within a single `PriorityChannel`. Two separate channels do not coordinate to form a unified priority queue.
- **Not a substitute for durability:** `PriorityChannel` is an in-memory queue. It does not automatically provide persistent storage across restarts, business retries, or transactions with external systems. If message recovery after failures is required, use an appropriate store or broker and configure endpoint transactions/retries as needed.
- **Monitor backlog:** implementations backed by `PriorityBlockingQueue` use an unbounded queue. An initial capacity parameter, when offered by your version's constructor, is an initial allocation size rather than a hard bound for back-pressure. Monitor queue depth, ingress/egress rates, age of the oldest message, and processing time; throttle producers or use a bounded mechanism/broker when backlog limits are needed.

Messages with a `correlationId` are still ordered by the comparator just like any other message. If messages in the same correlation group must be processed in business order, include sequence in the comparator or enforce ordering in a separate step. Attaching `correlationId` alone does not preserve arrival order.

## Verifying Behavior

A small test can verify that the comparator is applied as expected:

~~~java
PriorityChannel channel = new PriorityChannel();

channel.send(MessageBuilder.withPayload("low")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 1)
        .build());
channel.send(MessageBuilder.withPayload("high")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 9)
        .build());

assertThat(channel.receive(0).getPayload()).isEqualTo("high");
assertThat(channel.receive(0).getPayload()).isEqualTo("low");
~~~

When diagnosing unexpected ordering, check in order: did the producer attach the right priority header; is the header of type `Integer`; does the actual channel bean use the expected comparator; is the consumer reading from the right `PriorityChannel`; did another consumer dequeue the message first; and is the handler running concurrently causing completion order to differ from dequeue order?

## When to Use It?

| Runtime requirement | Recommended choice |
|---|---|
| Only need high-priority messages dequeued first | `PriorityChannel` with default comparator |
| Need tie-breaking by deadline or sequence | `PriorityChannel` with custom `Comparator<Message<?>>` |
| Need strict FIFO for the entire stream | Design appropriate serialization; do not rely solely on a priority queue |
| Need backlog limits or durable persistence | Choose a channel/broker with bounded capacity or persistence |
| Need fairness across priority classes | Add fairness policies rather than strict priority alone |

`PriorityChannel` solves one specific runtime decision: which message a consumer pulls next from this queue. Enforce priority policies at producers, keep the comparator pure and consistent, size the poller/concurrency to match handler capacity, and monitor backlog to detect starvation or insufficient consumption speed.
