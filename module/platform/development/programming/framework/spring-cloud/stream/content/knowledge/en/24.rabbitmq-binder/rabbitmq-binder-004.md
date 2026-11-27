# Exchange Type, Binding Routing Key, and routingKeyExpression

In RabbitMQ, producers send messages to an exchange; the exchange selects target queues based on the exchange type and declared bindings. With the Spring Cloud Stream RabbitMQ Binder, the `exchangeType` property determines how the exchange routes messages, `bindingRoutingKey` configures the key used when binding a queue to the exchange, and `routingKeyExpression` computes the routing key for each message emitted by a producer.

These three settings sit on opposite sides of the flow. The consumer creates the queue binding and selects the key pattern the queue wants to receive. The producer generates the actual routing key for the message. Both sides must align: whatever key the producer emits must match the queue's binding according to the exchange's rules.

## 1. Exchange, Queue, Binding, and Routing Key

In AMQP 0-9-1, producers do not send messages directly to queues. Producers publish messages to an exchange. The exchange uses bindings to decide which queue, stream, or other exchange receives the message.

| Component | Role |
|---|---|
| Exchange | Receives messages from producers and applies routing rules |
| Queue | Stores messages for consumers to receive and process |
| Binding | Links an exchange to a queue, along with a routing key or arguments if required by the exchange type |
| Routing key | Value attached by the producer on publish; the exchange uses it for routing depending on exchange type |
| Binding key | Key or pattern stored in a queue's binding |

Overview diagram:

~~~mermaid
flowchart LR
    P["Producer"] -->|"routing key"| E["Exchange"]
    E -->|"binding key / arguments"| Q1[("Queue A")]
    E -->|"binding key / arguments"| Q2[("Queue B")]
    Q1 --> C1["Consumer A"]
    Q2 --> C2["Consumer B"]
~~~

An exchange can have multiple bound queues. A message can be routed to one queue, multiple queues, or no queue, depending on the exchange type and bindings.

## 2. How Does the RabbitMQ Binder Map Destinations?

By default, the Spring Cloud Stream Rabbit binder maps each destination to a `TopicExchange`. When a consumer group is specified, the binder creates a queue in the form:

~~~text
<prefix><destination>.<group>
~~~

The queue is bound to the exchange with the default routing key `#` for non-partitioned destinations. If no group is declared, the binder creates an anonymous queue with a random name that is automatically deleted according to the consumer lifecycle.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-service
~~~

The default topology looks like:

~~~text
Exchange: orders.events (topic)
Queue:    orders.events.order-service
Binding:  orders.events -> orders.events.order-service, key #
~~~

With a topic exchange, the binding key `#` matches every routing key. Therefore, the default queue receives every message published to the `orders.events` exchange.

Rabbit binder properties related to routing:

| Property | Configuration side | Purpose |
|---|---|---|
| exchangeType | Consumer or producer | Selects the exchange type declared for the destination |
| bindingRoutingKey | Consumer; or producer when creating required groups | Selects the routing key/binding key used when binding the queue |
| bindingRoutingKeyDelimiter | Consumer or producer | Splits multiple binding keys from a single string |
| routingKeyExpression | Producer | Computes the actual routing key for each message |
| routingKey | Producer | Uses a fixed routing key |
| queueBindingArguments | Consumer | Supplies arguments for the binding, typically used with headers exchanges |

Rabbit-specific properties reside under `spring.cloud.stream.rabbit.bindings.<binding-name>.<consumer|producer>`. The `destination` and `group` properties reside under `spring.cloud.stream.bindings.<binding-name>`.

## 3. Four Common Exchange Types

RabbitMQ provides four basic exchange types: direct, topic, fanout, and headers. The Rabbit binder supports all four for non-partitioned destinations; for partitioned destinations, the binder supports direct, topic, and headers.

### 3.1. Direct Exchange: Exact Match

A direct exchange routes messages to queues whose binding key matches the message's routing key exactly. There are no wildcards.

Examples:

| Queue | Binding key | Message routing key | Receives message? |
|---|---|---|---|
| orders.created | order.created | order.created | Yes |
| orders.updated | order.updated | order.created | No |
| orders.audit | order.created | order.created | Yes |

A single routing key can match multiple identical bindings, so a direct exchange does not necessarily forward to only one queue. If two queues both bind with `order.created`, both receive the message.

Diagram:

~~~mermaid
flowchart LR
    P["Producer<br/>key = order.created"] --> E["Direct exchange"]
    E -->|"order.created"| A[("Queue created")]
    E -. "order.updated: no match" .-> B[("Queue updated")]
~~~

Example consumer configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        createdOrders-in-0:
          destination: orders.events
          group: created-orders
      rabbit:
        bindings:
          createdOrders-in-0:
            consumer:
              exchangeType: direct
              bindingRoutingKey: order.created
~~~

The producer must publish to the same destination with routing key `order.created`:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              exchangeType: direct
              routingKey: order.created
~~~

If the producer emits `order.updated`, the `created-orders` queue does not receive the message because the binding only accepts the `order.created` key.

### 3.2. Topic Exchange: Pattern Matching by Segments

A topic exchange splits routing keys into segments separated by dots (`.`). Binding keys can use two wildcards:

- `*` matches exactly one segment.
- `#` matches zero or more segments.

Examples:

| Binding key | Routing key | Match? | Reason |
|---|---|---|---|
| orders.* | orders.created | Yes | `*` matches the single segment `created` |
| orders.* | orders.eu.created | No | There are two segments after `orders` |
| orders.# | orders.eu.created | Yes | `#` matches multiple segments |
| orders.# | orders | Yes | `#` can match zero segments |
| *.created | orders.created | Yes | `*` matches `orders` |
| *.created | orders.eu.created | No | `*` matches only one segment |

Routing example:

~~~mermaid
flowchart LR
    P["Producer<br/>orders.eu.created"] --> E["Topic exchange"]
    E -->|"orders.* no match"| A[("Queue orders-one-level")]
    E -->|"orders.# match"| B[("Queue all-orders")]
    E -->|"orders.eu.* match"| C[("Queue eu-orders")]
~~~

Topic exchanges fit well when distributing events by a hierarchy such as region, event type, or domain. Examples of routing keys include `orders.eu.created`, `orders.us.cancelled`, and `payments.eu.completed`.

Configuring a queue that receives only order events in the EU region:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        euOrders-in-0:
          destination: business.events
          group: eu-orders
      rabbit:
        bindings:
          euOrders-in-0:
            consumer:
              exchangeType: topic
              bindingRoutingKey: orders.eu.#
~~~

The `business.events.eu-orders` queue receives keys like `orders.eu.created`, `orders.eu.cancelled`, or `orders.eu.refunded`, but not `orders.us.created`.

### 3.3. Fanout Exchange: Broadcasts to Every Bound Queue

A fanout exchange sends a copy of each message to every queue bound to the exchange. It ignores routing keys and binding keys.

Example:

~~~mermaid
flowchart LR
    P["Producer"] --> E["Fanout exchange"]
    E --> Q1[("Queue email")]
    E --> Q2[("Queue analytics")]
    E --> Q3[("Queue audit")]
~~~

Fanout is suited for notifications that need to be broadcast to multiple independent services—for example, a configuration update event that cache, audit, and analytics all need to receive.

Consumer configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        auditEvents-in-0:
          destination: system.notifications
          group: audit-service
      rabbit:
        bindings:
          auditEvents-in-0:
            consumer:
              exchangeType: fanout
~~~

Every queue bound to the `system.notifications` exchange receives the message. `bindingRoutingKey` and `routingKeyExpression` do not affect delivery in a fanout exchange because this exchange type ignores routing keys.

### 3.4. Headers Exchange: Routing by Headers

A headers exchange compares message headers against arguments in the binding. The routing key is not used for routing.

A binding can specify:

- `x-match: all`: all declared headers must match.
- `x-match: any`: at least one of the declared headers must match.

Example of a queue receiving only messages with `region=eu` and `eventType=order-created`:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        euOrderCreated-in-0:
          destination: business.events
          group: eu-order-created
      rabbit:
        bindings:
          euOrderCreated-in-0:
            consumer:
              exchangeType: headers
              queueBindingArguments:
                x-match: all
                region: eu
                eventType: order-created
~~~

The producer sends a message with the corresponding headers:

~~~java
Message<OrderEvent> message = MessageBuilder
    .withPayload(orderEvent)
    .setHeader("region", "eu")
    .setHeader("eventType", "order-created")
    .build();
~~~

If using `x-match: all`, the message must carry both headers with exact matching values. If using `x-match: any`, matching just one condition is enough. Headers exchanges fit when routing criteria depend on multiple message attributes rather than a single hierarchical routing key string.

## 4. Distinguishing bindingRoutingKey and routingKeyExpression

The two properties have similar names but act at different times:

| Property | Configured by | Applied when | Example |
|---|---|---|---|
| bindingRoutingKey | Consumer | When the binder binds the queue to the exchange | orders.eu.# |
| routingKeyExpression | Producer | Each time the producer sends a message | payload.region + '.' + payload.eventType |

`bindingRoutingKey` is the queue's subscription rule. `routingKeyExpression` generates the actual routing key on outgoing messages. With a topic exchange, the binding key often contains wildcards, while the message's routing key is a concrete value.

Example:

- Consumer binds the queue with `orders.eu.#`.
- Producer emits routing key `orders.eu.created`.
- The topic exchange matches and delivers the message to the queue.

If the producer emits `orders.us.created`, the EU queue does not receive the message. Setting the right expression on the producer side is not enough; the queue must have a matching binding key.

## 5. Using routingKeyExpression for Payload-Based Routing

`routingKeyExpression` is a SpEL expression evaluated when publishing a message. The expression can extract data from the payload or headers to build a dynamic routing key.

Suppose the payload is:

~~~java
public record OrderEvent(
    String orderId,
    String region,
    String eventType
) {}
~~~

The producer uses region and event type to construct the key:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: business.events
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              exchangeType: topic
              routingKeyExpression: "payload.region + '.' + payload.eventType"
~~~

With payload `region=eu`, `eventType=created`, the producer emits routing key `eu.created`. A consumer with binding key `eu.*` receives that message.

You can also read values from message headers:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routingKeyExpression: "headers['region'] + '.' + headers['eventType']"
~~~

If the message has headers `region=eu` and `eventType=created`, the generated key is `eu.created`. Ensure headers are always present and valid; an expression that fails on a missing header can cause publishing to fail.

### 5.1. Using a Fixed Routing Key

If every message needs the same routing key, use `routingKey` instead of an expression:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routingKey: orders.created
~~~

`routingKeyExpression` fits when the routing key depends on each message. `routingKey` is easier to read when the key is constant. There is no need to write a complex expression just to return a fixed string.

If using a SpEL expression to return a string literal, YAML requires escaping quotes per SpEL syntax. The binder documentation illustrates `routingKeyExpression: '''my.routingKey'''`; using the `routingKey` property is simpler for fixed keys.

### 5.2. Default Values

If neither `routingKey` nor `routingKeyExpression` is configured, the Rabbit producer binder uses the destination as the default routing key. For partitioned destinations, the default key takes the form `destination-<partition>`.

For consumer bindings, `bindingRoutingKey` defaults to `#`. Because the binder creates a topic exchange by default, the group queue receives all routing keys of the destination. When switching the exchange to `direct`, configure a binding key that matches the exact routing key emitted by the producer.

## 6. Configuring Multiple Binding Keys for One Queue

A queue may need to receive multiple groups of routing keys. The Rabbit binder supports a list of `bindingRoutingKey` values via `bindingRoutingKeyDelimiter`.

Example of a queue receiving both order creation and update events:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderChanges-in-0:
          destination: orders.events
          group: order-changes
      rabbit:
        bindings:
          orderChanges-in-0:
            consumer:
              exchangeType: direct
              bindingRoutingKey: "order.created,order.updated"
              bindingRoutingKeyDelimiter: ","
~~~

The binder creates two separate binding keys for the queue:

- `order.created`
- `order.updated`

With a topic exchange, you can combine multiple patterns such as `orders.eu.#,payments.eu.#`. Choose a delimiter that does not appear in the routing keys themselves to avoid incorrect splitting.

The producer `bindingRoutingKey` property can also apply to groups declared in `requiredGroups`. It only takes effect when the binder creates queues and bindings for those groups. If queues are managed manually or `bindQueue=false`, create the routing bindings on the broker according to the intended topology.

## 7. Keeping Exchange Type and Bindings Consistent

Producers and consumers typically reference the same destination, so they must agree on the exchange type. For example, a producer declaring `direct` while a consumer declares `topic` for the same exchange name creates an incompatible topology.

Example application with a `Supplier` emitting events and a `Consumer` receiving matching events:

~~~java
import java.util.function.Consumer;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String region, String eventType) {}

@Configuration
class OrderRoutingFunctions {

    @Bean
    Supplier<OrderEvent> publishOrder() {
        return () -> new OrderEvent("order-1001", "eu", "created");
    }

    @Bean
    Consumer<OrderEvent> consumeEuOrders() {
        return event -> System.out.println("EU order: " + event.orderId());
    }
}
~~~

Complete configuration template for a topic exchange:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder;consumeEuOrders
    stream:
      bindings:
        publishOrder-out-0:
          destination: business.events
        consumeEuOrders-in-0:
          destination: business.events
          group: eu-orders
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              exchangeType: topic
              routingKeyExpression: "payload.region + '.' + payload.eventType"
          consumeEuOrders-in-0:
            consumer:
              exchangeType: topic
              bindingRoutingKey: eu.#
~~~

In this example, both producer and consumer use the `business.events` exchange of type `topic`. The producer builds the routing key from the payload; the `eu-orders` group queue only receives keys starting with `eu`.

If the exchange already exists, the binder cannot change the exchange type simply by declaring a different `exchangeType`. RabbitMQ requires repeated declarations of the same name to have compatible attributes. If the exchange type mismatches, the broker may return `PRECONDITION_FAILED - inequivalent arg type`. Align the topology before deploying.

## 8. When Using a Headers Exchange

A headers exchange does not read routing keys. The producer must send the headers expected by the consumer binding; the queue binding must declare the matching arguments.

Example of two queues routing by region and event category:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        euPayments-in-0:
          destination: business.events
          group: eu-payments
        urgentEvents-in-0:
          destination: business.events
          group: urgent-events
      rabbit:
        bindings:
          euPayments-in-0:
            consumer:
              exchangeType: headers
              queueBindingArguments:
                x-match: all
                region: eu
                domain: payment
          urgentEvents-in-0:
            consumer:
              exchangeType: headers
              queueBindingArguments:
                x-match: any
                priority: urgent
                requiresAttention: true
~~~

The `eu-payments` queue requires both `region=eu` and `domain=payment`. The `urgent-events` queue receives messages when either `priority=urgent` or `requiresAttention=true` matches.

Do not use `*` or `#` wildcards for header values. Headers exchanges compare header values directly against binding arguments; they do not apply topic exchange wildcard syntax.

## 9. Using a Fanout Exchange for Broadcast

If every consumer group must receive every message, a fanout exchange is often simpler than a topic exchange with binding key `#`.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishSystemEvent-out-0:
          destination: system.events
        auditSystemEvent-in-0:
          destination: system.events
          group: audit
        metricsSystemEvent-in-0:
          destination: system.events
          group: metrics
      rabbit:
        bindings:
          publishSystemEvent-out-0:
            producer:
              exchangeType: fanout
          auditSystemEvent-in-0:
            consumer:
              exchangeType: fanout
          metricsSystemEvent-in-0:
            consumer:
              exchangeType: fanout
~~~

Each group has its own queue. The fanout exchange delivers one copy to each bound queue, so both `audit` and `metrics` receive the message. Whatever routing key the producer sets has no effect on the outcome.

## 10. Managing Pre-Existing Topology

By default, the Rabbit binder can declare exchanges, queues, and bindings. If the platform team has already pre-created the topology, decide which components the binder should declare itself.

To use an existing exchange and queue, the binder documentation illustrates:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        consumeExisting-in-0:
          destination: myExchange
          group: myQueue
      rabbit:
        bindings:
          consumeExisting-in-0:
            consumer:
              bindQueue: false
              declareExchange: false
              queueNameGroupOnly: true
~~~

With this configuration:

- `destination` is the existing exchange name.
- `group` is the existing queue name.
- `bindQueue=false` tells the binder not to bind the queue to the exchange automatically.
- `declareExchange=false` tells the binder not to declare the exchange automatically.
- `queueNameGroupOnly=true` uses the group name as the queue name, rather than concatenating destination and group.

The queue must already be bound to the exchange with the right routing key. When the binder does not create bindings, changing `bindingRoutingKey` in the application cannot alter manually managed topology.

## 11. Common Routing Errors

| Symptom | Possible cause | How to check |
|---|---|---|
| Consumer does not receive messages | Producer key does not match binding key | Inspect exchange type, routing key, and queue bindings |
| Direct exchange does not deliver messages | Binding key `#` is used while producer sends a key other than `#` | Set `bindingRoutingKey` to match the actual routing key |
| Topic exchange receives too many messages | Default `#` binding key | Narrow the binding key such as `orders.eu.#` |
| Topic exchange receives no messages | Wrong segment count or wildcard usage | Check that `*` matches one segment and `#` matches zero or more segments |
| Fanout does not deliver | Queue is not bound to the exchange | Inspect queue bindings; routing keys have no effect on fanout |
| Headers exchange receives no messages | Missing/mismatched header type or wrong `x-match` | Check message headers and `queueBindingArguments` |
| `PRECONDITION_FAILED` on startup | Same exchange name with mismatched type or declaration attributes | Compare broker topology with `exchangeType`, durability, and auto-delete |
| Publish succeeds but no queue receives | No matching binding or queue does not exist | Check publisher returns / alternate exchange and topology |
| Expression throws an error | Null payload/header or invalid SpEL expression | Safely log metadata and inspect input messages |

When routing behaves unexpectedly, check in order: destination/exchange, exchange type, queue, binding key or binding arguments, actual routing key, and message headers. Do not change `routingKeyExpression` alone while overlooking the queue's binding.

## 12. Testing Routing in Applications

Verify both topology configuration and actual message behavior.

### 12.1. Testing Producer Expressions

Create messages with different payloads or headers and verify the generated routing key is correct. Example:

| Payload | Expected routing key |
|---|---|
| region=eu, eventType=created | eu.created |
| region=us, eventType=cancelled | us.cancelled |
| region=apac, eventType=updated | apac.updated |

If the expression uses headers, also test missing-header cases to ensure errors are caught early.

### 12.2. Integration Tests with RabbitMQ

Run RabbitMQ using Testcontainers or a dedicated test environment, then:

1. Start the application with the Rabbit binder.
2. Verify the exchange is created with the expected type.
3. Verify the queue and binding key are created accurately.
4. Publish messages with matching and non-matching routing keys.
5. Verify the queue receives the expected subset of messages.
6. For headers exchanges, test both `x-match=all` and `x-match=any`.
7. Check publisher returns or alternate exchanges when messages are unroutable.

The Spring Cloud Stream Test Binder can test function flows and bindings at the application layer, but it does not replace integration tests against real RabbitMQ to verify exchange algorithms, wildcards, and queue bindings.

## 13. Guidelines for Choosing Exchanges and Routing

| Business requirement | Suitable exchange type | Routing approach |
|---|---|---|
| Receive only one exact event type or specific key | direct | Fixed `routingKey` and exact-matching `bindingRoutingKey` |
| Categorize by region, domain, or hierarchical event type | topic | `routingKeyExpression` builds key from payload; bindings use `*` and `#` |
| Broadcast to all subscribed queues | fanout | Create queue bindings; routing key does not matter |
| Select queues based on multiple header attributes | headers | `queueBindingArguments` and `x-match` |

Configuration workflow:

1. Determine whether a message goes to one queue or multiple queues.
2. Choose the exchange type based on distribution rules.
3. Design the routing key structure if using direct or topic.
4. Configure `routingKey` for fixed keys or `routingKeyExpression` for dynamic keys.
5. Configure `bindingRoutingKey` for each consumer queue.
6. For headers exchanges, define headers and `queueBindingArguments` on both sides.
7. Ensure producers and consumers agree on the exchange type.
8. Verify queues/bindings created by the binder or managed by the platform team.
9. Run integration tests verifying both matching and non-matching cases.

## Official References

- [Spring Cloud Stream RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html): exchange, queue, group model, and binder configuration.
- [RabbitMQ Binder - Consumer Properties](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html): `exchangeType`, `bindingRoutingKey`, `bindingRoutingKeyDelimiter`, and `queueBindingArguments`.
- [RabbitMQ Binder - Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html): `routingKeyExpression`, `routingKey`, and producer properties.
- [RabbitMQ - Exchanges](https://www.rabbitmq.com/docs/exchanges): direct, topic, fanout behavior, bindings, and exchange durability.
- [RabbitMQ - AMQP 0-9-1 Concepts](https://www.rabbitmq.com/tutorials/amqp-concepts): exchange types, headers exchanges, and routing mechanisms.
