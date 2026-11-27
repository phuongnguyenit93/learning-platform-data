# Publisher Confirms and Returns

## Learning Objectives

After this lesson, you will be able to:

- Explain what RabbitMQ **publisher confirms** are, at which boundary the broker emits **ACK/NACK** to the publisher, and why that confirmation is not a consumer ACK.
- Distinguish **publisher return (basic.return)** when a message is unroutable from **publisher confirm** when the broker confirms handling the publish.
- Configure **correlated confirms**, **publisher returns**, and **mandatory** in Spring Boot/Spring AMQP, tracking each message with **CorrelationData**.
- Explain the **UNKNOWN** state when connections drop or confirm deadlines expire, as well as duplicate-delivery risks during retries.
- Combine **RabbitTemplate**, an AMQP outbound channel adapter, and a **MessageChannel** in a Spring Integration flow with a one-way sending contract.
- Design **outbox, eventId, idempotent consumers, retry/backoff, dead-lettering**, and reconciliation processes aligned with reliability requirements.
- Test routed publishes, missing bindings, nonexistent exchanges, broker errors, slow confirms, and consumer processing failures.

## 1. Problem: Calling Publish Successfully Is Not Enough

Suppose **OrderService** saves an order and publishes **OrderCreated** to RabbitMQ. The application calls:

~~~java
rabbitTemplate.convertAndSend(
    "orders.events", "orders.created", "evt-1001|O-1001|150000");
~~~

This call can return **without a final verdict** on whether the broker accepted the publish, routed it to the expected queue, or whether the consumer finished processing. Therefore, immediately marking the event **DELIVERED_TO_WAREHOUSE** right after that call risks reporting a false state.

RabbitMQ and Spring AMQP provide two groups of signals on the publisher side:

1. **Publisher confirm:** broker confirms ACK or NACK for a publish operation under the confirms mechanism.
2. **Publisher return:** broker returns an **unroutable** message when mandatory/returns conditions are met.

The two mechanisms answer **two different questions**:

- **Confirm:** At what level did the broker handle/accept this publish?
- **Return:** Did any message fail to route to a matching queue?

~~~mermaid
flowchart LR
    S["OrderService<br/>OrderCreated"] --> C["MessageChannel"]
    C --> A["AMQP outbound adapter"]
    A --> RT["RabbitTemplate"]
    RT --> EX["RabbitMQ exchange"]
    EX -->|"Matching binding"| Q["Queue"]
    EX -. "Unroutable if mandatory" .-> RET["Publisher return"]
    EX -. "Publish ACK/NACK" .-> CON["Publisher confirm"]
    Q --> HC["Consumer"]
    HC -. "Consumer ACK/NACK" .-> Q
~~~

**Important:** RabbitMQ exchanges, queues, publisher confirms, publisher returns, and consumer acknowledgments sit at different boundaries. This lesson belongs to the **AMQP Adapter** chapter of **SPRING_INTEGRATION_ADAPTERS**, focusing on defining sending and error contracts for AMQP outbound adapters/gateways; the same completion-boundary mindset also helps when integrating File, SFTP, HTTP, JMS, Kafka, or databases.

## 2. Five Milestones Frequently Confused with One Another

| Milestone | Involved Component | What Can Be Observed | What Must Not Be Inferred |
| --- | --- | --- | --- |
| **MessageChannel.send() finishes** | Spring Integration | Channel handled the send call according to its semantics | RabbitMQ persisted the message or consumer processed it |
| **RabbitTemplate executes publish** | Spring AMQP/client | Client executed the publish call; may catch synchronous errors | Publisher confirm arrived or routing succeeded |
| **Publisher confirm ACK** | RabbitMQ → publisher | Broker confirmed the publish per confirms mechanism and queue/policy | Consumer read or committed business logic |
| **Publisher return** | RabbitMQ → publisher | Message could not be routed under conditions where broker returns it | Entire publish was rejected or consumer failed |
| **Consumer ACK** | Consumer → RabbitMQ | Consumer confirmed a delivery per ACK mode | Publisher received a business reply |

If the consumer needs to return **OrderAccepted** or **PaymentResult**, use a **request–reply gateway** or a separate business response workflow; publisher confirms/returns **do not turn a one-way outbound adapter into a gateway**.

### 2.1. A Contrasting Example

A producer publishes to exchange **orders.events**. The exchange exists, yet no binding matches routing key **orders.created**.

- The broker can still send a **publisher confirm ACK** because the publish operation was processed.
- If the publisher sets **mandatory=true**, returns are enabled, and no matching alternate route exists, the broker sends **basic.return** reporting the message as **unroutable**.
- If the publisher does not enable appropriate unroutable detection, the message reaches no queue while the caller sees no synchronous exception.

Thus, **looking only at confirm ACK is insufficient to claim the message reached the target queue**.

### 2.2. What Happens Once the Message Enters the Queue?

Even after RabbitMQ routes and stores the message in a queue, the consumer may be **offline**, waiting on a database, or hitting a schema error. Consumer ACK is a subsequent interaction between consumer and broker and does not automatically convert into a producer send result.

~~~mermaid
sequenceDiagram
    participant P as Publisher / RabbitTemplate
    participant X as RabbitMQ exchange
    participant Q as Queue
    participant C as Consumer
    P->>X: basic.publish(exchange, routing key, body)
    alt Matching binding exists
        X->>Q: Route message
    else Unroutable and mandatory
        X-->>P: basic.return
    end
    X-->>P: publisher confirm ACK/NACK
    Q-->>C: Delivery if message entered queue
    C-->>Q: Consumer ACK/NACK per mode
~~~

This diagram shows **types of events**, not a guarantee that every event fires for every message. For instance, if no queue receives the message, there is no consumer delivery; if confirms/returns are not configured, the publisher will not receive those callbacks.

## 3. How Do Publisher Confirms Work?

RabbitMQ publisher confirms are a confirmation mechanism **from broker to publisher**. Once confirm mode is enabled on a channel, the publisher can correlate publish calls with confirm ACKs/NACKs returned by the broker.

In the low-level RabbitMQ client, confirms tie to **publish sequence numbers** on an AMQP channel, and the broker can confirm one or multiple publishes per protocol rules. **Spring AMQP/RabbitTemplate** wraps most of these details so applications track them via callbacks or **CorrelationData**.

### 3.1. A Publisher ACK Is Not a Consumer ACK

Suppose the publisher receives an ACK for **evt-1001**. That signals the broker handled the publish at the durability level supported by the exchange/queue and current broker state. It **does not mean**:

- Warehouse received the delivery.
- Warehouse committed its database transaction.
- The consumer will never receive the message redelivered.
- Another Analytics application also finished.
- The rest of the workflow completed.

**Publisher confirm durability** still depends on queue type (classic/quorum), delivery mode, broker cluster setup, policies, and RabbitMQ version. Never claim "ACK means permanently persisted in every scenario."

### 3.2. Publisher Confirm NACK

The broker can send a NACK for a publish in scenarios where it cannot process the publish successfully under confirm semantics. A NACK is **not** a "payload failed schema validation" response from a consumer. Upon receiving a NACK, the publisher should record an error state, raise an alert, and consider retrying per business policy.

**Do not automatically interpret every NACK as a transient error** or retry infinitely. Collect error details, timestamps, broker health, and routing results to decide.

### 3.3. Async Confirms vs. Synchronous Waiting

There are two ways to observe outcomes:

- **Asynchronous:** send multiple messages and receive confirms via callbacks/futures. Good for throughput, but requires a tracking table for pending publishes.
- **Wait synchronously for one confirm:** caller waits until the broker confirms or times out. Easier to reason about for a single call, yet blocks threads, caps throughput, and timeouts still leave **UNKNOWN** state.

In Spring AMQP, tracking via **`CorrelationData.getFuture()`** is common when correlated confirms are enabled on supported versions. Never confuse a future completing with **ACK** with the consumer returning a business reply.

## 4. Publisher Returns and the Role of Mandatory

RabbitMQ publishes to an **exchange**. The exchange uses the routing key and bindings to decide which queues receive the message.

~~~mermaid
flowchart TD
    P["Producer"] --> X["Direct exchange<br/>orders.events"]
    X -->|"orders.created"| Q["orders.created.q"]
    X -. "Key matches no binding" .-> U["Unroutable"]
    U -->|"mandatory=true<br/>and returns handled"| R["Publisher return<br/>ReturnedMessage"]
    U -->|"mandatory=false<br/>no matching AE"| DROP["No receiving queue"]
~~~

### 4.1. What Information Does basic.return Carry?

When the broker returns an unroutable publish under **mandatory**, the return carries the **message** and diagnostic fields such as **reply code/text**, exchange, and routing key. Spring AMQP provides a corresponding data class to inspect returned messages.

A returned message tells you the message reached no target queue under routing rules at publish time. It does not mean a consumer read the message and rejected it; **this is a pre-delivery failure**.

### 4.2. Mandatory and Publisher Returns Must Work Together

To detect unroutable publishes at the RabbitTemplate level, you typically need:

- Returns enabled on the ConnectionFactory/client.
- **mandatory=true** on publishes where unrouted messages should be returned.
- A **ReturnsCallback** or returned-message handling path configured and tested.

If you enable only publisher confirms without proper mandatory/returns settings, an unroutable message can still receive a **publish-level ACK** from the broker.

### 4.3. Nonexistent Exchange vs. Unmatched Binding

| Scenario | Core Difference | Expected Signal |
| --- | --- | --- |
| Exchange **exists**, no matching binding | Published to a real exchange with no route target | `basic.return` when mandatory and conditions apply; confirm ACK may still arrive |
| Exchange **does not exist** | Published to a missing/wrong exchange resource | Protocol/channel error or publish failure; not necessarily `basic.return` |
| Queue exists, **no consumers** | Routed successfully, just nobody reading yet | Queue ready count grows; not a returned message |
| Consumer receives then **rejects/requeues** | Failure downstream of the queue | Consumer NACK/requeue/DLX, not publisher return |
| Connection drops before confirm | Publisher does not know whether broker received it | Timeout/connection error, UNKNOWN state |

### 4.4. Alternate Exchanges Affect Return Results

RabbitMQ can configure an **alternate exchange (AE)** to catch publishes the primary exchange cannot route. If a message successfully routes via the AE to a fallback queue, that can change whether the broker treats the message as unroutable and emits a return.

**Do not treat storing in an AE fallback queue as delivered to the intended business queue.** Monitor the fallback queue, alert on arrivals, and handle events that failed primary routing.

## 5. Implementation Architecture in Spring Integration

In a Spring Integration flow, an **AMQP outbound channel adapter** receives a Spring Message from a MessageChannel and uses RabbitTemplate to publish. Spring Message payloads and headers are not native RabbitMQ messages; the adapter, converter, and header mapper translate them as configured.

~~~mermaid
flowchart LR
    OS["OrderService"] --> MC["ordersToAmqp<br/>MessageChannel"]
    MC --> OA["AMQP outbound adapter"]
    OA --> RT["RabbitTemplate"]
    RT --> CF["ConnectionFactory"]
    CF --> EX["orders.events"]
    EX --> Q["orders.created.q"]
    CF -. "confirm/return" .-> TRACK["Publish tracking<br/>eventId + status"]
~~~

### 5.1. Channel Type Affects When the Caller Sees Errors

| Channel Before Outbound Adapter | Behavior | Risk |
| --- | --- | --- |
| **DirectChannel** | Publish handler runs synchronously on sender's thread | Caller sees synchronous exceptions, yet still does not know async confirm/return callbacks |
| **ExecutorChannel** | Publish runs on an executor | `send` succeeds on handoff; errors appear later on another thread |
| **QueueChannel** | Message is buffered for a polling consumer to publish | Needs capacity/poller and durable storage if crash recovery is required |

**`MessageChannel.send()` returning true does not replace publisher confirm.** Even with DirectChannel, future callbacks reporting ACK/return are separate from `send`'s boolean return. With ExecutorChannel, the gap widens further.

### 5.2. Outbound Adapter vs. Outbound Gateway

An **outbound adapter** suits one-way events: publish OrderCreated and let services react independently. An **outbound gateway** suits cases needing a **business reply** via AMQP request–reply, with reply-to, correlation, and timeout.

Publisher confirms only report **broker publish handling**, and publisher returns report **unroutable** status; they **do not give an outbound adapter a reply message** from the remote service.

### 5.3. Keeping eventId and Correlation Distinct

In our examples, we use:

~~~text
eventId: evt-1001                 (stable business identifier)
routingKey: orders.created       (RabbitMQ routing)
CorrelationData ID: evt-1001     (links publish to confirm outcome)
AMQP messageId: set separately   (for tracing if needed)
Spring MessageHeaders.ID: internal infrastructure ID
~~~

You can pass the same `eventId` string when constructing **CorrelationData** for one publish, while remembering CorrelationData ID serves **producer tracking** whereas `eventId` serves **business idempotency**. When retrying multiple times, you can generate an **attemptId** per attempt in your tracking table while keeping the **same `eventId`** for consumers to deduplicate.

## 6. Spring Boot Configuration for Publisher Confirms and Returns

In an application using **spring-boot-starter-amqp**, RabbitTemplate/ConnectionFactory are typically autoconfigured when conditions match. Configuration example for a publisher needing both confirms and returns:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Three properties serve distinct roles:

| Property | Role |
| --- | --- |
| **publisher-confirm-type: correlated** | Enables correlated publisher confirms via supported Spring AMQP mechanics |
| **publisher-returns: true** | Enables receiving returned message notifications |
| **template.mandatory: true** | Instructs the broker to return unroutable publishes under applicable conditions |

**Version note:** the configuration above is standard for modern Spring Boot/Spring AMQP. When upgrading, check exact property names and APIs for the version managed by your dependency management.

### 6.1. ConnectionFactory Must Be the Exact Bean Used by the Publisher

In Spring Boot, **CachingConnectionFactory** is usually the shared Spring AMQP ConnectionFactory for RabbitTemplate and listeners. If an application defines multiple ConnectionFactories or custom RabbitTemplates, enabling confirms on one factory **does not give confirms to a template using another factory**.

When publishes succeed without callbacks firing, check:

- Which **ConnectionFactory** RabbitTemplate actually injects.
- Whether that factory has **correlated publisher confirms and returns** enabled.
- Whether the publish path sets **mandatory** appropriately.
- Whether a callback/future or tracking component is **actually listening**.
- Whether the connection dropped before the broker sent results.

### 6.2. When Creating a Custom RabbitTemplate

If multiple endpoints share one RabbitTemplate, do not let independent services overwrite each other's **ConfirmCallback** or **ReturnsCallback**. Use a centralized publish tracker, separate templates with distinct roles, or callback mechanisms properly managed by Spring Integration.

**Defining a custom RabbitTemplate bean can alter Boot autoconfiguration**; verify that the resulting template has the intended MessageConverter, mandatory flag, and connection factory.

### 6.3. Permissions and Topology

The publisher needs write permission to the exchange in the correct RabbitMQ virtual host. Exchanges, queues, and bindings must be provisioned by an authorized RabbitAdmin/AmqpAdmin or external infrastructure. **Declaring a Queue bean does not mean the broker already has that queue.**

Separate publisher accounts from topology-admin accounts if security policy dictates. In production, load username/password from a secret manager, enable TLS properly, and avoid printing credentials or sensitive payloads in logs.

## 7. Spring AMQP Example: Topology and RabbitTemplate

Let's build a publisher emitting **OrderCreated** to a direct exchange:

~~~text
Exchange:      orders.events
Routing key:   orders.created
Queue:         orders.created.q
Payload:       eventId|orderId|totalVnd
Example:       evt-1001|O-1001|150000
~~~

This is an illustrative contract to keep focus on confirms/returns. Real applications should use **JSON with eventType/schemaVersion**, validation, and managed serializers.

### 7.1. Spring Boot Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-amqp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-integration</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Versions should align with the Spring Boot BOM. Depending on your setup, the broker and topology are created automatically via RabbitAdmin/AmqpAdmin or provisioned externally.

### 7.2. Declaring Exchange, Queue, and Binding

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersAmqpTopology {
    public static final String EXCHANGE = "orders.events";
    public static final String ROUTING_KEY = "orders.created";
    public static final String QUEUE = "orders.created.q";

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue(QUEUE, true);
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue, DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
            .to(ordersExchange)
            .with(ROUTING_KEY);
    }
}
~~~

**Durable** exchanges and queues help preserve topology across restarts, which does not mean every message is persisted and processed once by consumers. Check **delivery mode**, queue type, confirms, and idempotency separately.

### 7.3. Dedicated RabbitTemplate for Publish Tracking

To use a centralized ReturnsCallback, you can define a dedicated RabbitTemplate for publishing OrderCreated:

~~~java
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersPublisherTemplateConfiguration {

    @Bean("ordersPublisherTemplate")
    public RabbitTemplate ordersPublisherTemplate(
            ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);

        // Requires publisher returns to be enabled at the connection factory.
        template.setMandatory(true);
        template.setReturnsCallback(returned -> {
            System.err.println(
                "Unroutable exchange=" + returned.getExchange()
                    + ", key=" + returned.getRoutingKey()
                    + ", code=" + returned.getReplyCode()
                    + ", text=" + returned.getReplyText());
        });

        return template;
    }
}
~~~

This is a **dedicated template**, preventing one service from overwriting a ReturnsCallback registered by another on a shared template. With Spring Boot's **publisher-returns: true** property, verify the ConnectionFactory injected into this bean actually has returns and correlated confirms enabled. The callback logs merely for illustration; **never treat logs as durable publish-state storage**.

**Warning:** If the application only needs a single RabbitTemplate and relies on Spring Boot's autoconfigured bean, you can use that template with unified callback configuration. Declaring manual beans can change autoconfiguration conditions; avoid adding multiple RabbitTemplate beans without qualifiers and causing injection ambiguity.

## 8. Tracking Each Publish with CorrelationData

**CorrelationData** lets Spring AMQP attach confirm results to a specific publish operation. When both correlated confirms and returns are active, returned-message data for unroutable publishes can also be attached to the corresponding publish.

We use two identifiers:

- **eventId** (e.g., `evt-1001`): business identity, **unchanged** across retries.
- **attemptId** (UUID): identity of each publish attempt, **can change** across retries to track individual attempts.

### 8.1. Publisher with Confirm Future

~~~java
import java.util.UUID;

import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ConfirmTrackedOrderPublisher {
    private final RabbitTemplate rabbitTemplate;

    public ConfirmTrackedOrderPublisher(
            @Qualifier("ordersPublisherTemplate")
            RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        if (eventId == null || !eventId.matches("[A-Za-z0-9_-]{1,80}")
                || orderId == null
                || !orderId.matches("[A-Za-z0-9_-]{1,80}")
                || totalVnd <= 0) {
            throw new IllegalArgumentException("OrderCreated invalid");
        }

        String body = eventId + "|" + orderId + "|" + totalVnd;
        String attemptId = UUID.randomUUID().toString();
        CorrelationData correlation = new CorrelationData(attemptId);

        try {
            rabbitTemplate.convertAndSend(
                OrdersAmqpTopology.EXCHANGE,
                OrdersAmqpTopology.ROUTING_KEY,
                body,
                correlation);
        } catch (RuntimeException ex) {
            // Publisher outcome might be unknown after some network failures.
            System.err.println(
                "Send exception: event=" + eventId
                    + ", attempt=" + attemptId);
            throw ex;
        }

        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null || confirm == null) {
                System.err.println(
                    "Confirm unavailable: " + attemptId);
            } else if (!confirm.isAck()) {
                System.err.println(
                    "Broker NACK: " + attemptId);
            } else if (correlation.getReturned() != null) {
                System.err.println(
                    "Broker ACK but unroutable: " + attemptId);
            } else {
                System.out.println(
                    "Broker ACK and no return: " + attemptId);
            }
        });
    }
}
~~~

**Example assumptions:** A Spring AMQP version supporting `CorrelationData.getFuture()`, correlated publisher confirms, and returned-message correlation; RabbitTemplate configured with mandatory and a connection factory supporting returns. Verify exact APIs for your library version.

### 8.2. Interpreting Results Correctly

| Condition | Careful Interpretation | Recommended Handling |
| --- | --- | --- |
| Future completes with **ACK**, **no returned message** | Broker confirmed publish; no unroutable observed under configured mechanics | Reached publisher confirm milestone, **not yet consumer processed** |
| Future **ACK**, with **returned message** | Broker processed publish yet could not route to a queue per contract | Mark **UNROUTABLE**, fix routing/topology |
| Future **NACK** | Broker did not confirm publish success | Record error state, investigate, retry if appropriate |
| Future completes exceptionally | Normal confirm result unavailable | Record error/UNKNOWN, reconcile |
| No confirm before deadline | Uncertain whether broker received it | **UNKNOWN**, do not mark definitely FAILED |
| `convertAndSend` throws exception | Synchronous error, may occur before or after partial effect | Classify root cause; if uncertain whether broker received it, idempotency is still required |

**Never equate "no returned message" with absolute certainty that every target queue received it.** That conclusion depends on whether mandatory/returns are truly active, connection state, alternate exchanges, topology, and other policies. With fanout or multiple target queues, publisher confirms still do not prove each downstream business handler completed.

### 8.3. ReturnedMessage and Callback Ordering

In Spring AMQP versions supporting correlated returns, **returned message** details are attached to CorrelationData before the corresponding confirm future completes when that feature is active. Thus you can inspect **`correlation.getReturned()`** when handling the confirm.

However, never correlate events by **log timestamp order** or assume callbacks always run on the same thread. In practice, concurrent publishes can confirm out of send order. Persist structured **attemptId** and `eventId` records.

### 8.4. Why the Demo Callback Is Insufficient for Production

The code above only logs; it does not yet:

- Persist state before publishing.
- Enforce a maximum confirm wait deadline per attempt.
- Release tracking resources promptly.
- Handle restarts before callbacks arrive.
- Prevent unintended concurrent sends of the same eventId.
- Update an **outbox** and retry after failures.
- Prove consumer business outcomes.

**Do not run database transactions or long blocking HTTP calls directly inside the callback thread** without an appropriate concurrency/lifecycle design. Hand results off to a controlled worker/publish-tracking service.

## 9. Using RabbitTemplate in a Spring Integration AMQP Outbound Flow

Spring Integration lets business code send a **Spring Message** to a channel; the **AMQP outbound adapter** handles publishing through RabbitTemplate:

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.amqp.dsl.Amqp;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrdersIntegrationFlow {

    @Bean
    public MessageChannel ordersToAmqp() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow ordersOutbound(
            @Qualifier("ordersPublisherTemplate")
            RabbitTemplate rabbitTemplate) {
        return IntegrationFlow.from("ordersToAmqp")
            .handle(Amqp.outboundAdapter(rabbitTemplate)
                .exchangeName(OrdersAmqpTopology.EXCHANGE)
                .routingKey(OrdersAmqpTopology.ROUTING_KEY))
            .get();
    }
}
~~~

Example producer sending a Spring Message to the channel:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class OrdersChannelPublisher {

    private final MessageChannel ordersToAmqp;

    public OrdersChannelPublisher(
            @Qualifier("ordersToAmqp") MessageChannel ordersToAmqp) {
        this.ordersToAmqp = ordersToAmqp;
    }

    public void publish(String eventId, String orderId, long totalVnd) {
        String payload = eventId + "|" + orderId + "|" + totalVnd;
        boolean accepted = ordersToAmqp.send(
            MessageBuilder.withPayload(payload)
                .setHeader("businessEventId", eventId)
                .build());

        if (!accepted) {
            throw new IllegalStateException(
                "MessageChannel did not accept message");
        }
    }
}
~~~

**Pick a single publishing path per event:** either `ConfirmTrackedOrderPublisher` calling RabbitTemplate directly, or `OrdersChannelPublisher` going through the Spring Integration outbound adapter. Calling both for one business operation sends two publishes.

### 9.1. Note on Correlation in the Outbound Adapter

Having correlated confirms on RabbitTemplate **does not automatically make the outbound adapter build CorrelationData from businessEventId and provide complete application tracking**.

If you need ACK/NACK/return handling at the **Spring Integration message** level, use the confirm correlation options and confirm/return notification channels supported by your **Spring Integration AMQP version**, and test:

1. A Spring Message with `eventId` passes through the adapter.
2. Each confirm/return result correlates to the right event/attempt.
3. A confirm ACK that is unroutable is not falsely marked delivered.
4. Messages lacking tracking metadata follow an explicit policy.
5. Asynchronous errors are not ignored just because `MessageChannel.send()` returned.

The Java DSL example above illustrates a **one-way publish path**. `ConfirmTrackedOrderPublisher` in Section 8 illustrates building CorrelationData directly. Do not treat the two examples as equivalent in tracking behavior without configuring the outbound adapter's confirm options.

### 9.2. Payload Types and Type Conversion

In the example, the String payload is converted by RabbitTemplate's converter into AMQP body bytes. If you need JSON DTOs, configure an appropriate MessageConverter/transformer and schemaVersion; never assume the internal **businessEventId** header automatically appears intact in AMQP properties.

Critical business identifiers can live inside the payload by contract so consumers can still deduplicate even if header mappers change. **Content type, charset, eventType, and schemaVersion** must be verified with contract tests.

### 9.3. Does a Reply Message Appear on the Outbound Adapter?

**Not a business reply by default.** An outbound channel adapter is a one-way endpoint. Confirm ACKs and publisher returns are signals about publishing, distinct from a business response message. If a flow needs a reply from another service, use an outbound gateway or an event-based workflow with explicit business correlation.

## 10. The UNKNOWN State: Broker May Have Received, Publisher Does Not Know

The hardest case is not always NACK or return, but **receiving no clear answer at all**.

~~~mermaid
sequenceDiagram
    participant A as Order publisher
    participant R as RabbitMQ
    participant D as Tracking store
    A->>D: Save event evt-1001 = PENDING
    A->>R: basic.publish(evt-1001)
    R->>R: May have routed and stored message
    Note over A,R: Connection lost / confirm never returns
    A->>D: UNKNOWN (insufficient evidence)
    A->>D: Schedule reconciliation or safe retry
    A->>R: Resend same eventId if needed
    Note over R: Possible duplicate delivery<br/>Consumer needs idempotency
~~~

At the disconnect point, the publisher **cannot know for sure** whether the broker received the publish. Marking it **FAILED_UNSENT** and resending without deduplication risks executing consumer side effects twice. Marking it **SUCCESS** when the broker never got it risks losing the event.

**UNKNOWN is not a cosmetic label**; it is a genuine distributed-systems outcome where observation was insufficient. Persist state and define an explicit next-step policy.

### 10.1. Suggested State Machine

~~~mermaid
flowchart TD
    N["NEW / PENDING"] --> S["SENDING<br/>attemptId"]
    S -->|"ACK + no return observed"| C["PUBLISH_CONFIRMED"]
    S -->|"Returned unroutable"| U["UNROUTABLE"]
    S -->|"Broker NACK"| F["RETRYABLE_FAILURE<br/>or investigate"]
    S -->|"Exception / timeout<br/>insufficient evidence"| UN["UNKNOWN"]
    F --> RET["Bounded retry + backoff"]
    UN --> RECON["Reconcile + idempotent retry"]
    RET --> S
    RECON --> S
    U --> FIX["Fix topology / route"]
~~~

These states are **application-designed examples**, not built-in enums of RabbitTemplate or Spring Integration. Even **PUBLISH_CONFIRMED** only marks a broker milestone and must not be interpreted as **BUSINESS_COMPLETED**.

### 10.2. Minimum Data in Publish Tracking

| Field | Why Needed |
| --- | --- |
| **eventId** | Stable business identifier across send attempts |
| **attemptId** | Distinguishes individual publish attempts, pairs with CorrelationData |
| **exchange / routingKey** | Reconciles topology/routing |
| **schemaVersion / contentType** | Records the contract of the emitted payload |
| **attemptCount / nextRetryAt** | Caps retries and drives backoff |
| **lastError / returnedInfo** | Diagnoses NACK, unroutable, and timeouts |
| **lastSentAt / confirmedAt** | Tracks latency and expiration |
| **status** | Drives recovery after restart |

If payloads must be stored for replay, persist the **body or a durable reference** to that data rather than `eventId` alone. Critical events also need retention, PII, and tracking-store access policies.

### 10.3. Timeout Must Be a Deadline, Not a Conclusion of Broker Rejection

A send attempt can time out due to:

- Slow or dropped network connection.
- Overloaded broker or publisher flow control.
- Delayed callback delivery.
- Application callback worker falling behind.
- Process restart before receiving the outcome.

Missing a timely confirm is **not enough** to conclude the broker never received the message. Confirm deadlines should follow SLA targets and pair with a **timeout sweeper** capable of resolving attempts stuck in `SENDING`.

## 11. Retry, eventId, and Idempotent Consumers

When a publisher retries after NACK, timeout, or connection loss, the broker may receive **multiple publishes of the same business event**. RabbitMQ does not automatically provide exactly-once business execution across producer, queue, consumer, and database.

### 11.1. A Sequence That Can Produce Duplicates

1. Producer publishes OrderCreated with **eventId = evt-1001**.
2. Broker routes the message and may send a confirm, which the publisher fails to receive.
3. Producer retries with the **same eventId**.
4. Consumer receives two deliveries containing `evt-1001`.
5. Consumer must detect `eventId` was already applied, avoiding two orders or deducting inventory twice.

~~~mermaid
flowchart LR
    P["Producer retry<br/>evt-1001"] --> Q["RabbitMQ queue"]
    Q --> C["Consumer"]
    C --> D{"Inbox already has<br/>evt-1001?"}
    D -->|"No"| T["Transaction:<br/>business + mark processed"]
    D -->|"Yes"| SK["Skip duplicate side effect"]
~~~

**Never replace the business payload's eventId with a retry's new CorrelationData ID.** CorrelationData tracks each individual publish attempt; `eventId` deduplicates across all receiving sides.

### 11.2. What Must Be Protected on the Consumer?

With a **processed_event** table holding a unique key on **consumer_name + event_id** or an appropriate business key:

- If the event has not been processed, mark it and execute side effects inside a data transaction when possible.
- If the event was already processed, return/ACK per policy **without repeating side effects**.
- If two deliveries execute concurrently, the unique constraint must prevent race conditions.
- If `eventId` matches while payload/schema differs, raise a conflict rather than silently treating it as a valid duplicate.

Idempotency is the **consumer's responsibility** whenever side effects must be protected. A broker ACK to the publisher cannot replace a database unique constraint.

### 11.3. Retries Must Distinguish Error Categories

| Error | Typical Nature | Action to Consider |
| --- | --- | --- |
| Broker temporarily unavailable | Recoverable | Bounded retry, backoff, and jitter |
| Connection lost near confirm | Uncertain outcome | UNKNOWN + idempotent retry or reconciliation |
| Broker confirm NACK | Broker failed to confirm publish | Record error, retry/alert per policy |
| Unroutable due to missing binding | Topology mismatch, usually config error | Quarantine/alert, fix binding before replaying |
| Nonexistent exchange | Config/topology error | Check permissions, exchange declaration, migrations |
| Payload serialization error | Permanent data/contract error | Fix data; do not hot-retry |
| Missing publish permissions | ACL/credential issue | Fix permissions or account; do not retry infinitely |
| Consumer parse error | Post-queue failure | Consumer retry/DLQ policy, not publisher return |

**Backoff** prevents retry storms while the broker is unhealthy. **Jitter** keeps multiple instances from retrying at the exact same instant. Cap attempts, deadlines, queued work, and tracking resources; never retry infinitely on an HTTP caller thread.

## 12. Transactional Outbox Coordinating Database and AMQP

A typical sequence:

~~~text
OrderService writes order to database
       |
       v
RabbitTemplate publishes OrderCreated
~~~

If the application crashes **after committing the order but before publishing**, no corresponding event reaches the broker. If publishing succeeds but it crashes **before recording sent status**, the event may be published again. Publisher confirms tell you the broker handled the publish, yet **do not create an atomic transaction spanning the database and RabbitMQ**.

### 12.1. The Outbox Pattern

~~~mermaid
flowchart LR
    S["OrderService"] --> TX["DB transaction"]
    TX --> O[("Orders")]
    TX --> OB[("OutboxEvent")]
    OB --> W["Outbox publisher worker"]
    W --> RT["RabbitTemplate<br/>CorrelationData"]
    RT --> MQ["RabbitMQ"]
    MQ --> C["Idempotent consumer"]
    RT -. "Confirm / Return / UNKNOWN" .-> W
    W --> OB
~~~

A sound implementation can:

1. Write **Order** and **OutboxEvent** in the **same database transaction**.
2. Have a worker pick up pending events, record an attempt, and publish via RabbitTemplate or an AMQP outbound adapter.
3. Track **confirm ACK/NACK**, **returned messages**, and timeouts.
4. Mark the publish milestone per policy; if UNROUTABLE or UNKNOWN, never conflate with business completion.
5. On worker restart, read unfinished events and retry with the **old eventId** and a new attemptId.
6. Use an inbox/idempotency check on the consumer to prevent duplicate side effects.

### 12.2. Why Not Mark Outbox SENT Immediately After convertAndSend?

A normal **`convertAndSend`** call does not wait for correlated confirm results. If you mark the outbox `SENT` right after the method returns, the publish might:

- Match no binding and be returned.
- Receive a broker NACK.
- Lose connectivity before the outcome is known.

**SENT** must have an explicit architectural/business definition. A safer milestone is **PUBLISHED_CONFIRMED** once broker ACK arrives and no return is observed under configured mechanics; **BUSINESS_PROCESSED** requires separate confirmation from the consumer if mandated.

### 12.3. Outbox Is Not Exactly-Once

An outbox provides a **durable replay source** and closes the gap between DB commit and publish. It **does not** guarantee an event is published only once in all circumstances. Workers can retry after lost confirms or crashes between publishing and updating status. Consumer idempotency remains required.

### 12.4. Publisher Confirms vs. RabbitMQ Transactions

RabbitMQ offers its own channel transaction mechanisms, yet enabling them does not automatically create an atomic transaction shared with OrderService's database. Publisher confirms are usually preferred when tracking publishes at good throughput, paired with a durable outbox and consumer idempotency as required.

Never blend **RabbitMQ publisher confirms**, **Spring transaction managers**, **JDBC transactions**, and **consumer ACKs** into one vague commit concept.

## 13. Publisher Returns Are Not Dead-Letter Queues

This confusion frequently causes data loss:

| Mechanism | Stage Where It Acts | Role |
| --- | --- | --- |
| **Publisher return** | When an exchange cannot route a publish under mandatory | Notifies producer of unroutable message |
| **Alternate exchange** | When primary exchange cannot route and an AE exists | Lets broker route via fallback exchange |
| **Dead-letter exchange (DLX)** | After a message enters a queue and is dead-lettered per rule | Routes failed/expired/limit-exceeded deliveries elsewhere |
| **Retry queue / delayed retry** | Specific retry architecture | Delays reprocessing by time |
| **Outbox/error store** | Producer side before/during/after publish | Preserves publish intent and state on publish failure |

### 13.1. Unroutable Example

~~~text
Publisher -> orders.events (existing exchange)
           -> routingKey = orders.unknown
           -> no matching binding
           -> mandatory=true => basic.return back to publisher
~~~

The publisher can detect this routing error even with no consumer running. **The consumer's DLQ never receives the message** because it was never routed into the primary queue.

### 13.2. Consumer Dead-Letter Example

~~~text
Publisher -> orders.events
           -> orders.created.q
           -> consumer receives yet fails JSON parsing
           -> reject/NACK requeue=false
           -> DLX/DLQ if queue is configured properly
~~~

This is a separate scenario. The publisher may already have received a confirm ACK earlier, while the consumer failed to process and the delivery was dead-lettered per policy.

### 13.3. Alternate Exchanges and Alerting

If using an **alternate exchange** to capture unroutable messages, design the fallback queue, retention, DLQ, and investigation tooling. Never ignore messages piling up in an AE thinking "the publisher saw no return so everything is fine." An event sitting in a routing-fallback queue **still has not reached the intended business consumer**.

## 14. Throughput, In-Flight Confirms, and Load Capacity

Publisher confirms create a stream of ACK/NACK signals from broker to producer. When publishing fast, many publishes may be **awaiting confirms** simultaneously. Without bounding tracked pending attempts, memory can grow and destabilize the application when the broker slows down.

### 14.1. Ways to Structure Confirms

| Model | Advantage | Risk / Trade-off |
| --- | --- | --- |
| **Send one message, wait for confirm** | Simple per-message reasoning | High latency, low throughput when RTT is significant |
| **Send a batch, wait for all** | Amortizes per-message wait overhead | Hard to tell which message needs retry without granular tracking |
| **Async correlated confirms** | Keeps many publishes in-flight | Must bound pending count, correlate each result, manage timeouts and restarts |

Spring AMQP **CorrelationData** and confirm callbacks facilitate asynchronous tracking, yet the application must still design:

- **Pending count/limit:** how many unconfirmed publishes may be in-flight at once?
- **Queue capacity:** how does the publisher worker handle backpressure when the broker slows?
- **Timeout:** when does an attempt transition to `UNKNOWN`?
- **Retry scheduling:** are backoff, caps, jitter, and hot-loop prevention in place?
- **Shutdown:** where are unresolved attempts durably stored?

### 14.2. Keep Heavy Work Out of Callbacks

Confirm/return callbacks may execute on Spring AMQP I/O or infrastructure threads. Running slow SQL transactions, blocking HTTP calls, or sleeps inside a callback can stall processing of other confirms.

A better design: the callback builds a **small result** containing attemptId, status, and timestamp, handing it to a worker/tracking service responsible for database updates. If cross-thread handoff is in-memory, pair it with an **outbox timeout sweeper** to recover un-updated publishes after crashes.

### 14.3. Measuring the Right Bottleneck

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Slow publish calls | Network, blocked connection, overloaded broker | Connections, broker alarms, publish latency |
| Rising confirm latency | Broker/queue persistence, load, network, or slow callbacks | Confirm p50/p95/p99, pending count |
| Rising NACKs | Broker unable to accept publish as expected | Broker logs, NACK reason if present, retries |
| Rising returns | Wrong binding/routing or altered topology | Exchange, routing key, queues/bindings, AE |
| Pending confirms stuck too long | Dropped connection, lost callbacks, or overloaded app | Timeout sweeper, connection events, tracking |
| Producer ACKs healthy yet queue backlog grows | Slow or offline consumer | Queue ready/unacked, consumer count, ACK rate |
| Low consumer processing despite small queue | Misrouted messages, rejected/DLQ, premature ACKs | Route rate, returns, DLQ, business metrics |

**Adding publisher threads does not automatically make RabbitMQ or consumers faster.** Optimization must account for broker capacity, message size, queue durability, connections/channels, producer confirms, and consumer throughput.

### 14.4. Payload Size and Broker Durability

Publishing large messages increases network, memory, serialization CPU, and broker confirm latency. If an event involves a multi-hundred-MB SFTP file, send **metadata/a reference to object storage** instead of stuffing the entire file into an AMQP body unless limits and trade-offs have been thoroughly evaluated.

Queue type (classic/quorum), message persistence, cluster replication, broker disk flow control, and network latency all affect confirm duration. Never copy a local confirm timeout directly to production where durability and traffic differ.

## 15. Testing Publisher Confirms and Returns

Sending one message and seeing a consumer log line is **not enough** to verify reliability. Build tests that actively exercise different broker and routing conditions.

### 15.1. Mandatory Test Matrix

| Case | Condition | Signal / Outcome to Verify |
| --- | --- | --- |
| **Valid route** | Valid exchange, queue, binding | Confirm ACK per mechanism; no return; queue/consumer receives message |
| **Missing binding** | Exchange exists, routing key unmatched | Return fires when mandatory/returns enabled; confirm may still ACK |
| **Nonexistent exchange** | Publish to wrong exchange name | Channel/protocol or publish error; not treated as normal return |
| **Broker stopped before publish** | No connection | Exception/attempt failure; outbox does not mark publish confirmed |
| **Broker lost near confirm** | Broker may have received publish | UNKNOWN/timeout; retry preserves eventId |
| **Missing ReturnsCallback** | Unroutable publish, mandatory/returns misconfigured | Test detects missing observability rather than passing falsely |
| **Confirms disabled** | ConnectionFactory lacks correlated confirms | Future/callback fails to operate as expected; startup/config validation catches it |
| **Out-of-order callbacks** | Multiple concurrent publishes | Correlated by attemptId, never log order |
| **Large message** | Payload exceeds size limit | Converter/broker error traced and resource limits respected |
| **Consumer offline** | Valid route, zero consumers | Queue backlog grows; no publisher return just for missing consumer |
| **Consumer reject** | Malformed JSON post-delivery | Consumer DLQ/ACK policy applies, not publisher return |
| **Alternate exchange** | Key misses primary exchange, AE present | Message lands in alternate queue per policy, alerted differently from main route |
| **Publisher restart** | Outbox has unresolved attempts | Events recover; idempotency prevents duplicate side effects |
| **Peak load** | Many concurrent events | Pending confirms, heap, latency, retries, callbacks without loss |

### 15.2. Testing Correlated Confirm on a Valid Route

In an integration test running against a **dedicated test RabbitMQ**:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class PublisherConfirmIntegrationTest {

    private final RabbitTemplate rabbitTemplate;

    public PublisherConfirmIntegrationTest(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Test
    void routedPublishGetsConfirm() throws Exception {
        CorrelationData data =
            new CorrelationData(UUID.randomUUID().toString());

        rabbitTemplate.convertAndSend(
            "orders.events",
            "orders.created",
            "evt-test-1|O-test-1|150000",
            data);

        CorrelationData.Confirm confirm =
            data.getFuture().get(5, TimeUnit.SECONDS);

        assertNotNull(confirm);
        assertTrue(confirm.isAck());
        // Check the return condition separately if mandatory is enabled.
        assertTrue(data.getReturned() == null);
    }
}
~~~

**Test prerequisites:** RabbitTemplate must use a ConnectionFactory with correlated confirms and returns, proper mandatory configuration, and **orders.events** actually bound to **orders.created.q**. This snippet illustrates awaiting the future; it does not automatically prove the consumer committed.

In a real JUnit/Spring Boot test, set up a test context and inject RabbitTemplate properly—for example via Spring test extensions and integration configuration—rather than copying this class as a standalone unit test without injection and expecting it to run.

### 15.3. Testing Returned Messages When No Route Exists

In an **isolated test broker**, publish to a valid exchange with a routing key that matches no binding:

~~~java
CorrelationData data =
    new CorrelationData("attempt-unroutable-1");

rabbitTemplate.convertAndSend(
    "orders.events",
    "orders.key.that.does.not.exist",
    "evt-test-2|O-test-2|150000",
    data);

CorrelationData.Confirm confirm =
    data.getFuture().get(5, TimeUnit.SECONDS);

// With publisher confirms and returns correctly configured:
// confirm can be ACK, while data.getReturned() is non-null.
// The returned message provides exchange, routing key and reply info.
~~~

Do not write tests expecting a **mandatory NACK** on unroutable messages: the broker can issue a publish-level **ACK** alongside sending a **return**. With an alternate exchange that has a matching route, behavior can also differ; tests must know the test broker's topology.

### 15.4. Why Tests Must Verify Both Broker and Application State

A test checking only the CorrelationData future does not prove the outbox worker wrote **PUBLISH_CONFIRMED** or **UNROUTABLE** accurately. For production flows, verify:

1. Attempts are persisted **before sending**.
2. ACK/NACK/return/timeout map to the exact `attemptId` and `eventId`.
3. Outbox state updates idempotently.
4. If the process dies before updating, unfinished events recover.
5. Consumers handle duplicates safely when the broker redelivers the same event.

### 15.5. Testcontainers/Integration Tests vs. Unit Tests

**Unit tests** can verify confirm/return classification functions and state machines using mocks without a broker. However, they **do not prove** the broker actually sends `basic.return`, the channel has confirms enabled, or queue bindings exist. Back those behaviors with **integration tests against real RabbitMQ in a test environment**, alongside converter contract and data-handling tests.

## 16. Observability and Operating the Publisher

Publisher confirms/returns need clear observability. An application reporting an endpoint as RUNNING while publisher returns spike can still be **failing to deliver messages to the target queue**.

### 16.1. Recommended Metrics

| Suggested Metric | Purpose |
| --- | --- |
| **publish_attempt_total** | Publish attempts started per eventType/destination |
| **publish_confirm_ack_total** | Publishes ACKed by broker |
| **publish_confirm_nack_total** | Publishes NACKed by broker |
| **publish_return_total** | Returned messages (unroutable) |
| **publish_unknown_total** | Attempts expired or uncertain |
| **publish_pending_count** | Attempts currently awaiting confirmation |
| **publish_confirm_latency** | Latency from publish to confirm |
| **outbox_pending_age** | Age of events waiting to be published |
| **outbox_retry_total** | Retry count |
| **queue_ready/unacked** | RabbitMQ backlog state |
| **consumer_business_success_total** | Business events actually processed by consumers |

These are **suggested metric names**, not a promise that Spring Integration/RabbitTemplate automatically emits these exact names. Use Micrometer, Spring observations, or custom instrumentation per library version and architecture.

### 16.2. Reading Metrics in Context

- **High confirm ACKs, high returns:** broker handles publishes, yet routing is misconfigured.
- **High confirm ACKs, growing ready queue:** producer sends fine; consumers are slow or offline.
- **High confirm ACKs, low business success:** inspect consumer DLQ, converters, business logic, or premature ACKs.
- **Growing pending confirms, high latency:** check broker/network/callback bottlenecks or backpressure.
- **Rising UNKNOWN after deploy:** inspect ConnectionFactory, callbacks, shutdown handling, and deadlines.
- **NACKs rising alongside broker disk alarms:** investigate broker/queue policies rather than merely raising retry rates.

### 16.3. Safe Logging

Do not log full payloads containing personal data or credentials. A useful log entry:

~~~text
eventId=evt-1001
attemptId=7f31...
exchange=orders.events
routingKey=orders.created
publishStatus=UNROUTABLE
replyCode=312
retryable=false
~~~

**`replyCode=312`** is just an example of the common **NO_ROUTE** code in AMQP `basic.return`, not a substitute for reading the actual code from the returned message. Do not assume different reply codes share the same root cause.

### 16.4. Lifecycle and Graceful Shutdown

When shutting down the application:

1. Stop accepting new events from upstream sources or persist unpublished events to a durable outbox.
2. Stop launching new publish attempts.
3. Give pending confirms a bounded grace window to settle.
4. Record or retain `UNKNOWN` status for attempts without a definitive result.
5. Close endpoints/connections according to Spring's lifecycle; do not close a shared ConnectionFactory arbitrarily.
6. On restart, workers read the outbox, reconcile, and retry safely.

**Do not treat a clean ApplicationContext shutdown as proof that every publisher confirm arrived and the outbox synced.** Test shutdown under publish bursts, network drops, and in-flight callbacks.

### 16.5. Security

Producers need appropriate **write** permissions on the exchange in the right virtual host; topology-management users need **configure** permissions when declaring exchanges/queues/bindings. Enforce least privilege, enable TLS, load credentials from a secret manager, and restrict logging of sensitive headers/payloads.

A returned message can carry the entire original body. **Never dump the full returned body into production logs** if it holds user data or sensitive transactions.

## 17. Architecture Scenario: Ordering and Multiple Receiving Systems

OrderService must publish OrderCreated for **Warehouse** and **Analytics**. Requirements:

- Once an Order is committed, there must be a way to replay the event if RabbitMQ is temporarily unavailable.
- An event is logically emitted **once in business logic**, even if retried multiple times at the transport layer.
- Warehouse and Analytics have **separate queues** so each system receives OrderCreated.
- The publisher knows whether the broker accepted the event without returning it; if uncertain, state is preserved.
- Consumers avoid duplicate side effects from redeliveries or republished attempts.

### 17.1. Reference Design

~~~mermaid
flowchart TD
    OS["OrderService"] --> DBTX["DB transaction"]
    DBTX --> O[("Orders")]
    DBTX --> OB[("OutboxEvent<br/>stable eventId")]
    OB --> W["Publisher worker"]
    W --> RT["RabbitTemplate<br/>CorrelationData"]
    RT --> EX["orders.events<br/>exchange"]
    EX --> WQ["warehouse.orders.q"]
    EX --> AQ["analytics.orders.q"]
    WQ --> WC["Warehouse consumer<br/>inbox / idempotency"]
    AQ --> AC["Analytics consumer<br/>inbox / idempotency"]
    RT -. "ACK/NACK/return/timeout" .-> TRACK["Publish tracker"]
    TRACK --> OB
~~~

With a direct exchange, both queues can bind using the same key **orders.created**; or use a topic exchange with binding patterns as needed. The producer does not need to publish twice just because two consumer groups exist, unless a contract explicitly requires two separate publishes.

### 17.2. Questions to Finalize Before Implementation

1. **Success milestone:** is broker confirm without return sufficient, or must Warehouse send a business acknowledgment?
2. **Identifiers:** where are `eventId` and `attemptId` generated and persisted across restarts?
3. **Contract:** JSON/Avro payload, schemaVersion, contentType, routing key?
4. **Topology:** do platform tools provision exchanges, queues, and bindings; who can modify them?
5. **Failure policy:** on UNROUTABLE or NACK, retry or pause and alert?
6. **UNKNOWN:** when confirms are lost, what are the deadline and reconciliation/replay steps?
7. **Consumer:** how are duplicate writes prevented and ACK, retry, and DLQ managed?
8. **Observability:** how are confirmed outbox entries reconciled against business-processed events at each consumer?

### 17.3. Distinguishing "Published" from "Processed"

| State Known to OrderService | Safe to Claim | Not Safe to Claim Yet |
| --- | --- | --- |
| Outbox NEW | Event emission intent recorded in DB | Broker received it |
| Publisher ACK, no return observed | Publisher confirm milestone reached per config | Warehouse/Analytics finished processing |
| Publisher UNROUTABLE | Route missed target queues per contract at publish time | Consumer received or will self-heal |
| Publisher UNKNOWN | Final outcome of publish attempt is unknown | Definitely never sent |
| Separate Warehouse business ACK | Warehouse confirmed business outcome per contract | Analytics definitely processed it |

If OrderService's HTTP API returns **202 Accepted** after committing Order + Outbox in a transaction, that means **accepted for asynchronous processing**, not that all downstream work is finished. Define caller-facing statuses clearly.

### 17.4. Connection to SFTP/File/HTTP in This Module

Another flow ingests CSV files via SFTP, normalizes records, and publishes AMQP events:

~~~mermaid
flowchart LR
    S["SFTP CSV"] --> IA["SFTP inbound adapter<br/>poller"]
    IA --> V["Parse + validate"]
    V --> DB["Durable import/outbox"]
    DB --> AM["AMQP outbound adapter<br/>RabbitTemplate"]
    AM --> MQ["RabbitMQ"]
    MQ --> C["Consumer"]
~~~

In this scenario:

- SFTP poller picking up the file is the **data ingestion milestone**.
- DB/outbox recording events to publish is the **internal durability milestone**.
- Publisher confirms/returns are the **AMQP delivery milestone**.
- Consumer ACK and business commit are the **receiving processing milestone**.

Do not delete source files or mark an entire import pipeline successful solely because `MessageChannel.send()` returned true if the contract requires durable publishing or downstream completion.

## 18. Common Mistakes

**"`RabbitTemplate.convertAndSend` returning without exception means the broker ACKed."** The send call and confirm callback/future happen at different times. Enable and track confirms explicitly.

**"Publisher ACK means it definitely entered the right queue."** An unroutable publish can still be ACKed by the broker. Use mandatory/returns or appropriate topology controls.

**"Unroutable always produces a NACK."** Publisher returns and publisher confirm NACKs are different signals; an unroutable message can receive a publish-level ACK.

**"No consumers means the message must be returned."** Messages can route into a queue and wait; zero consumers does not invalidate a binding.

**"A nonexistent exchange also produces a returned message."** Publishing to a missing exchange typically causes protocol/channel errors, unlike an existing exchange with no route.

**"`publisher-returns=true` alone is enough."** Mandatory must also be applied, and a callback/tracking path must be properly configured.

**"Enabling correlated confirms gives durable tracking automatically."** CorrelationData futures live in memory inside the process; if the process crashes, pending states need separate durable recovery.

**"Confirm callbacks arrive in send order."** Concurrent publishes can confirm out of order; correlate using attemptId.

**"CorrelationData ID is the consumer's deduplication key."** Consumers need a business `eventId` stable across retries; the publisher's `attemptId` may change.

**"Timeout means the broker definitely did not receive it."** When connections drop near confirms, the outcome is UNKNOWN; retries must be idempotent.

**"Retrying every error is safe."** Never hot-retry missing bindings, insufficient permissions, or invalid schemas; fix the root cause.

**"Publisher return sends the message into a DLQ."** Returns report routing failure from exchange to publisher; DLX/DLQ belongs to queue dead-lettering in different scenarios.

**"Routing via an alternate exchange means the primary consumer received it."** Messages in an alternate queue are often fallback records awaiting investigation.

**"Outbox + confirms = end-to-end exactly-once."** Producers can resend and consumers can receive duplicates; idempotency remains mandatory.

**"Marking outbox SENT right after `convertAndSend` suffices."** If the required milestone is broker-confirmed, wait for future/callback/return outcomes before updating.

**"Logging the full body of returned messages is harmless."** Returned bodies may hold sensitive data; log only safe metadata and needed error codes.

**"With ExecutorChannel, `send` still catches publish errors synchronously."** Publishing may run on another thread; async errors need dedicated handling.

**"A durable queue guarantees the consumer processed it."** Queue durability, publisher confirms, and consumer business outcomes are three separate dimensions.

**"Enabling confirms on one ConnectionFactory covers every RabbitTemplate."** With multiple factories/templates, verify the exact beans wired into each endpoint.

## 19. Practical Deployment Checklist

Before shipping an AMQP publishing flow to production, answer every item below:

| Area | Conditions to Verify |
| --- | --- |
| **Routing** | Exchange/routing key/bindings in the right virtual host; target queues exist |
| **Confirms** | Correlated confirms actually enabled on the ConnectionFactory used by RabbitTemplate |
| **Returns** | `publisher-returns` and `mandatory` enabled; listener/tracker handles returned messages |
| **Correlation** | Stable eventId, distinct attemptId per publish; callbacks correlate accurately |
| **Conversion** | Schema, contentType, charset, allowed headers, and DTOs compatible |
| **Timeout** | Deadline defined for pending confirms and `UNKNOWN` state persisted durably |
| **Retry** | Bounded retries, backoff/jitter, no hot loops on permanent errors |
| **Outbox** | Publish intent recorded in the business transaction when zero event loss is required |
| **Idempotency** | Consumer enforces unique constraint/inbox or equivalent deduplication |
| **Capacity** | Limits on pending publishes, queue capacity, and callback workload |
| **Broker** | Queue type/persistence/cluster policy meets SLA; broker alarms monitored |
| **Consumer** | ACK/retry/DLQ tested; business outcome monitored independently |
| **Shutdown** | Pending attempts resolved or persisted for retry after restart |
| **Security** | TLS, least-privilege ACLs, no hardcoded credentials, no sensitive payloads in logs |
| **Tests** | Unroutable, missing exchange, timeout, NACK, restart, and load tests verified |

### 19.1. When to Choose Publisher Confirms/Returns?

**Use them** whenever an application must verify broker-level publish outcomes and catch unroutable errors, especially for critical events or multi-consumer/multi-queue topologies. **You do not have to force every best-effort notification** into a heavy outbox if business requirements tolerate message loss—just document that SLA explicitly.

If the requirement is **immediate business processing results**, confirms/returns are not enough: use a request–reply gateway or a callback/event response architecture. If the requirement is **no lost events after DB commit**, add an outbox or equivalent durable store; confirms/returns are only one part of the complete solution.

## 20. Self-Check Questions

1. What question does publisher confirms answer about a publish? How does it differ from a consumer ACK?
2. Why does `RabbitTemplate.convertAndSend` returning without an exception not prove the broker confirmed?
3. When an exchange exists with no matching binding, can the broker send both a return and a confirm ACK?
4. What conditions are typically required for RabbitTemplate to receive publisher returns?
5. How does a nonexistent exchange differ from an existing exchange with no route?
6. Why does a queue having no consumers not necessarily cause messages to be returned?
7. What problem does `CorrelationData.getFuture()` solve? Can it replace a durable outbox?
8. How should `eventId` and `attemptId` be designed when an event is retried three times?
9. Why does losing connectivity before confirm yield `UNKNOWN` rather than definitely `FAILED`?
10. When receiving a publisher ACK while `CorrelationData.getReturned()` is non-null, how should the publish status be interpreted?
11. When an alternate exchange is configured, how can return behavior and message placement change?
12. How does a publisher return differ from a dead-letter exchange in terms of when the message is processed?
13. Why should a publisher callback not perform long blocking I/O without delegating to a separate worker?
14. With DirectChannel vs. ExecutorChannel, how does the caller's ability to observe synchronous exceptions differ?
15. Why does an AMQP outbound adapter not become a gateway just by enabling confirm ACKs?
16. What gap between a database transaction and RabbitMQ publishing does a transactional outbox close?
17. Why does an outbox still need an idempotent consumer even when the publisher enables correlated confirms?
18. When the broker ACKs yet the Warehouse consumer is offline, what should be monitored next?
19. Which metrics distinguish routing errors, slow broker confirms, and slow consumer business processing?
20. If SFTP inbound ingests a file successfully yet the RabbitMQ publish becomes `UNKNOWN`, should the file be deleted and the whole pipeline marked successful? Why?

## Summary

**Publisher confirms and returns** are two distinct mechanisms for observing AMQP publishes through RabbitMQ. **Publisher confirm ACK/NACK** reflects how the broker handled a publish under confirm semantics; **publisher return** reports that a message could not route to any matching queue when **mandatory/returns** apply. A message can **receive a confirm ACK yet still be returned**. Conversely, **consumer ACKs and business replies** occur at a different boundary and cannot be substituted by a publish confirmation.

In Spring Integration, an **AMQP outbound channel adapter** passes Spring Messages from a **MessageChannel** to RabbitTemplate, yet applications needing reliability verification must properly configure **ConnectionFactory, correlated confirms, mandatory, returns, and CorrelationData**, and verify how the adapter propagates results back into the flow for their library version. For critical events, designs need **stable eventIds, per-attempt attemptIds, UNKNOWN states, bounded retries, an outbox, idempotent consumers, routing tests, and metric-driven operations**. Only by clearly separating **send called**, **broker ACKed**, **message routed**, and **business completed** can an AMQP integration system recover reliably.
