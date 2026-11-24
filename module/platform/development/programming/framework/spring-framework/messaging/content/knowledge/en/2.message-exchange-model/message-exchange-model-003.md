# Work Queues and Competing Consumers

## 1. Problem and Objectives

A system receives many background tasks such as sending emails, processing images, generating reports, synchronizing data, or calculating invoices. If all of these run directly on the HTTP request thread, response times will depend on the processing time of each task. Under heavy load, the application can easily run out of threads, time out, or slow down interactive user-facing features.

A work queue decouples the moment a request is accepted from the moment it is executed. The producer sends a message describing the task to a broker; the broker stores the message in a queue; a consumer retrieves the message, processes it, and confirms completion. Multiple consumers can listen to the same queue to share the load. This pattern is commonly called competing consumers.

After this lesson, the reader will be able to:

- Distinguish a work queue from publish/subscribe and understand why a message in competing consumers is normally delivered to only one consumer at a time.
- Explain how the broker distributes messages, prefetch, acknowledgement, and redelivery.
- Create a durable queue and multiple concurrent consumers with Spring AMQP.
- Estimate the impact of consumer count, processing time, and prefetch on throughput.
- Design error handling, retries, dead-letter queues, idempotency, and processing order.
- Recognize the limits of delivery guarantees and choose an implementation suited to the business domain.

## 2. Work Queues and Competing Consumers

### 2.1. Components

A work queue has three main roles:

1. **Producer** creates the task and sends the message to the broker. The producer does not need to know which consumer will process it.
2. **Broker** receives the message, routes it into a queue, and manages message delivery to consumers.
3. **Consumer** receives the message, performs the work, and acknowledges the outcome according to the broker's protocol.

For example, an order service can send a GenerateInvoice message to the invoice.work queue. Multiple workers running in the same application or across multiple application instances can register consumers on that queue.

~~~mermaid
flowchart LR
    P[Producer] --> B[Message broker]
    B --> Q[(invoice.work)]
    Q --> C1[Consumer A]
    Q --> C2[Consumer B]
    Q --> C3[Consumer C]
~~~

Consumers reading from the same queue are competing receivers. The broker delivers each message to one consumer per delivery. While a consumer is processing a message, the broker normally keeps the message in an unacknowledged state; that message is not yet considered complete. Only when the consumer acknowledges success can the broker remove the processed message from the queue.

### 2.2. One Message for One Consumer or for All Subscribers?

Two models should be distinguished:

| Model | Distribution | Use Cases |
|---|---|---|
| Competing consumers on one queue | Each message is delivered to one consumer in the group; consumers split the work | Sending emails, processing images, generating reports, processing orders |
| Publish/subscribe with multiple queues | One event is broadcast to multiple independent queues; each subscriber group receives a copy of the event | An OrderCreated event needs to update inventory, send an email, and record analytics |

If three consumers listen to the same work queue, a message is not automatically processed three times. If three systems all need to receive an event, route the event to three independent queues or subscriptions. Do not create three competing consumers and expect each consumer to receive every message.

### 2.3. Why Is It Called “Competing”?

Consumers compete to take the next unit of work from the queue. When a consumer is free and the broker can deliver a message, that consumer receives it. A slower consumer gets fewer opportunities to receive new messages if the broker limits unacknowledged messages with a low prefetch count.

Competition here is a load-sharing mechanism, not an exclusive lock at the business layer. It does not guarantee that two messages related to the same order will be processed in order, nor does it prevent two different tasks from updating the same record concurrently. Those constraints must be addressed at the data layer or via message partitioning.

## 3. Message Delivery Lifecycle

A typical processing flow consists of these steps:

1. The producer creates a message with an identifier and the required data.
2. The producer sends the message to the broker's exchange or routing address.
3. The broker routes the message into a queue.
4. The broker delivers the message to a consumer that has capacity for more work.
5. The consumer validates the data, executes the business logic, and writes the result.
6. Upon successful processing, the consumer acknowledges (ack) the message.
7. The broker removes the acknowledged message from the pending state.

If the consumer crashes or loses its connection before acking, the broker can redeliver the message to another consumer. This prevents losing work when a worker fails, but creates the possibility that a message is processed more than once.

### 3.1. Acknowledgement

Acknowledgement is confirmation from the consumer that a message has been processed according to the delivery policy.

With Spring AMQP, the listener container normally uses the AUTO acknowledgement mode: the container acks after the listener method finishes normally. If the listener throws an exception, the container handles reject/nack according to its configuration. MANUAL mode lets the application explicitly ack or nack, though it also increases the responsibility of managing state and handling every error branch.

Do not ack immediately upon receiving a message if the work has not yet finished. If a worker acks first and then crashes midway, the broker believes the work is done and will not redeliver it. Conversely, if the business logic has committed to the database but the worker crashes before acking, the broker may redeliver the message. Therefore, handlers must tolerate repeated execution.

### 3.2. At-Most-Once, At-Least-Once, and Exactly-Once

- **At-most-once**: messages are not redelivered; a message can be lost if the consumer fails after receiving it but before completing processing.
- **At-least-once**: messages are redelivered when no successful confirmation is received; reduces the risk of losing work but can produce duplicate deliveries.
- **Exactly-once**: the business effect takes place exactly once. This guarantee cannot be inferred solely from using a queue or ack. A system can deliver a message multiple times yet still produce a single business effect through idempotency or deduplication.

In most job-processing systems, at-least-once combined with an idempotent handler is the practical choice. Design for redelivery from the start.

## 4. Load Sharing, Concurrency, and Prefetch

### 4.1. Increasing the Number of Consumers

Suppose a job takes an average of 2 seconds. One consumer processing sequentially has a theoretical capacity of about 0.5 jobs/second. Three consumers can process in parallel at about 1.5 jobs/second if the broker, CPU, database, and downstream services all have sufficient capacity.

This is only an ideal estimate. Actual throughput also depends on:

- Average processing time and the variance of processing times.
- The number of active consumers and the number of threads each consumer uses.
- Prefetch and the number of messages currently in an unacknowledged state.
- The capacity of the database, HTTP APIs, filesystem, or external services.
- Serialization/deserialization, network, and broker connection overhead.
- Retries, redeliveries, locks, and resource contention.

Adding consumers does not always increase throughput. If all workers write to a table with a hot lock or call a rate-limited API, adding more workers only increases contention, timeouts, and retry counts.

### 4.2. Prefetch

Prefetch limits the number of messages the broker can deliver to a consumer that have not yet been acknowledged. With a prefetch of 1, each consumer holds at most one unacknowledged message. Only after completing and acking does the consumer receive the next message. This approach generally distributes work fairly evenly when processing times vary per message.

A high prefetch can improve throughput by reducing message delivery wait times, but comes with trade-offs:

- A fast consumer can hold many messages in memory while other consumers sit idle.
- Messages that have been delivered but not yet finished are no longer in the ready portion of the queue; queue depth metrics may lead operators to underestimate the backlog in progress.
- When a consumer crashes, many unacknowledged messages may be redelivered at once.
- Increasing prefetch increases memory usage and the number of in-flight tasks.

There is no single optimal prefetch value for all systems. For long-running tasks or uneven processing times, starting at 1 is easy to observe. For short, uniform tasks that can be batched, you can increase it gradually while measuring throughput, latency, and memory.

### 4.3. Spring Listener Concurrency

Spring AMQP can create multiple consumers for the same listener endpoint. The `concurrency` attribute on `@RabbitListener` determines the initial number of concurrent consumers. When running multiple application instances, the total number of consumers is the sum of consumers across all instances.

For example: 4 instances, each with concurrency 3, create around 12 consumers on the same queue. Account for this total when sizing connections, CPU, database pools, and external service quotas. Do not look only at the instance count while ignoring the consumer count inside each instance.

## 5. Runnable Example with Spring AMQP and RabbitMQ

The example below creates a durable queue named `demo.work.queue`, sends 12 jobs, and runs three competing consumers on that queue. Each consumer simulates processing for 700 ms. The program uses Java 17 and Spring Boot 3.3.13.

### 5.1. Project Structure

~~~text
work-queue-demo/
├── compose.yaml
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/workqueue/
        │       ├── WorkQueueApplication.java
        │       ├── WorkQueueConfig.java
        │       ├── WorkPublisher.java
        │       └── WorkConsumer.java
        └── resources/
            └── application.properties
~~~

### 5.2. Starting RabbitMQ

Create `compose.yaml`:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:3.13-management
    container_name: work-queue-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: demo
      RABBITMQ_DEFAULT_PASS: demo123
    ports:
      - "5672:5672"
      - "15672:15672"
~~~

The demo credentials are only for a local learning environment. Do not use this password in production environments.

Start the broker:

~~~bash
docker compose up -d
~~~

RabbitMQ AMQP listens on port 5672; the default management UI is at http://localhost:15672 with username `demo` and password `demo123`.

### 5.3. Declaring Maven Dependencies

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>work-queue-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-amqp` provides Spring AMQP, `RabbitTemplate`, the listener container, and Spring Boot configuration integration.

### 5.4. Connection and Listener Configuration

Create `src/main/resources/application.properties`:

~~~properties
spring.application.name=work-queue-demo

spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
spring.rabbitmq.username=demo
spring.rabbitmq.password=demo123

# Each consumer holds at most one unacknowledged message.
spring.rabbitmq.listener.simple.prefetch=1
~~~

Prefetch is set to 1 to make it easy to observe work distribution across the three consumers. The example uses the listener container's default acknowledgement: when the listener finishes normally, the message is acked.

### 5.5. Declaring the Queue

Create `WorkQueueConfig.java`:

~~~java
package com.example.workqueue;

import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WorkQueueConfig {

    public static final String WORK_QUEUE = "demo.work.queue";

    @Bean
    Queue workQueue() {
        return QueueBuilder.durable(WORK_QUEUE).build();
    }
}
~~~

`durable(true)` preserves the queue declaration across broker restarts. This does not automatically guarantee that every message is durable: queue durability and message delivery mode are two separate properties. A production system also needs publisher confirms and appropriate persistence policies.

### 5.6. Spring Boot Application

Create `WorkQueueApplication.java`:

~~~java
package com.example.workqueue;

import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableRabbit
public class WorkQueueApplication {

    public static void main(String[] args) {
        SpringApplication.run(WorkQueueApplication.class, args);
    }
}
~~~

`@EnableRabbit` enables processing of methods annotated with `@RabbitListener`.

### 5.7. Competing Consumers

Create `WorkConsumer.java`:

~~~java
package com.example.workqueue;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class WorkConsumer {

    @RabbitListener(
        queues = WorkQueueConfig.WORK_QUEUE,
        concurrency = "3"
    )
    public void handle(String task) throws InterruptedException {
        String worker = Thread.currentThread().getName();

        System.out.printf("%s received %s%n", worker, task);
        Thread.sleep(700);
        System.out.printf("%s completed %s%n", worker, task);
    }
}
~~~

`concurrency = "3"` instructs the listener container to create three consumers. All three register on `demo.work.queue`; the broker delivers each message to one consumer per delivery. `Thread.sleep` only simulates time-consuming work; do not use it to wait in real business code.

### 5.8. Producer Sending Tasks

Create `WorkPublisher.java`:

~~~java
package com.example.workqueue;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class WorkPublisher implements CommandLineRunner {

    private final RabbitTemplate rabbitTemplate;

    public WorkPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    @Override
    public void run(String... args) {
        for (int i = 1; i <= 12; i++) {
            String task = "task-" + i;
            rabbitTemplate.convertAndSend(
                WorkQueueConfig.WORK_QUEUE,
                task
            );
            System.out.println("Sent " + task);
        }
    }
}
~~~

When using `RabbitTemplate`'s `convertAndSend(routingKey, message)` overload, the message is sent through the default exchange with the queue name as the routing key. The queue was declared via the bean in the previous step.

### 5.9. Running the Program

Requirements: JDK 17+, Maven, and Docker Compose.

~~~bash
docker compose up -d
mvn spring-boot:run
~~~

The logs will show lines for sending, receiving, and completing tasks. The actual thread names are generated by Spring; the ordering of messages across workers depends on scheduling and processing time. You may see one worker receive `task-1`, another receive `task-2`, and the remaining worker receive `task-3`; after a worker acks a job, it can receive the next message.

Do not use one specific log ordering as the sole criterion for correctness. The criterion for this example is that all 12 messages are processed, up to three listeners can process concurrently at a time, and each message is delivered to only one consumer in the group per delivery.

Stop the application with Ctrl+C; stop the broker when no longer needed:

~~~bash
docker compose down
~~~

## 6. Error Handling and Redelivered Messages

### 6.1. Consumer Crashing Mid-Processing

Suppose a consumer receives `task-7`, begins updating data, and then the process terminates before acking. The broker detects that the consumer connection has been lost and can return the message to a deliverable state. Another consumer can then receive `task-7`.

This is necessary behavior for recovery, but it also means handlers must tolerate redelivery. Never assume a message appears only once over its entire lifecycle.

### 6.2. Classifying Errors

Not every error should be retried:

- **Transient errors**: network timeouts, an external service temporarily unavailable, recoverable deadlocks. These can be retried with backoff.
- **Permanent data or business errors**: missing required fields, invalid status codes, non-existent accounts. Infinite retries will not fix the data.
- **System errors requiring investigation**: mapping bugs, code bugs, incompatible schemas. Log sufficient context and bound the number of attempts.

With RabbitMQ, rejecting a message can requeue or dead-letter it depending on the reject flag and queue configuration. The default requeue behavior is not a complete retry strategy. If a failing message is immediately requeued, consumers can repeatedly receive the same message, causing a hot loop and stalling queue progress.

### 6.3. Bounded Retries and Dead-Letter Queues

A production design typically includes:

1. A limit on the number of attempts.
2. Increasing delays between attempts, such as 1 second, 5 seconds, 30 seconds.
3. A dead-letter exchange/queue (DLX/DLQ) for messages that have exhausted their attempts or cannot be processed.
4. Observability tooling and a process to inspect, fix data, and replay messages in a controlled manner.

A DLQ is a quarantine area for failed messages to be investigated. It does not fix messages by itself and should not be treated as indefinite storage. Set alerts when the DLQ grows, and define who investigates, how to replay, and how to avoid replaying messages that already produced business effects.

### 6.4. Example Queue-Level DLQ Configuration

With RabbitMQ, you can declare a dedicated dead-letter exchange and queue. The snippet below illustrates how to bind the work queue to a DLX:

~~~java
@Bean
DirectExchange deadLetterExchange() {
    return new DirectExchange("demo.work.dlx");
}

@Bean
Queue deadLetterQueue() {
    return QueueBuilder.durable("demo.work.dead").build();
}

@Bean
Binding deadLetterBinding(
        Queue deadLetterQueue,
        DirectExchange deadLetterExchange) {
    return BindingBuilder.bind(deadLetterQueue)
        .to(deadLetterExchange)
        .with("demo.work.dead");
}

@Bean
Queue workQueue() {
    return QueueBuilder.durable(WorkQueueConfig.WORK_QUEUE)
        .deadLetterExchange("demo.work.dlx")
        .deadLetterRoutingKey("demo.work.dead")
        .build();
}
~~~

This snippet extends the queue configuration in the previous example; when applying it, replace the old `workQueue()` bean with the DLX-enabled version and add the imports for `DirectExchange`, `Binding`, and `BindingBuilder`. To limit the number of retries, combine it with a retry policy or retry queues using TTL and dead-letter routing. Declaring a DLQ alone does not create a retry limit.

## 7. Idempotency: Handling Duplicates Without Duplicate Effects

Idempotency is the property where processing the same request multiple times produces the same business outcome as processing it once. This is a critical line of defense when using at-least-once delivery.

For example, an invoice-creation message should carry a stable `eventId` or `taskId`. Before applying changes, the consumer checks whether the identifier has already been processed. An inbox table can use a unique key on `event_id`:

~~~sql
CREATE TABLE processed_message (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Within the same database transaction:

1. Attempt to insert `event_id` into the `processed_message` table.
2. If the key already exists, treat this as a duplicate message and do not repeat the business logic.
3. If the insert succeeds, apply the business changes.
4. Commit the transaction.
5. Let the listener container ack the message after the listener completes normally.

Handle duplicate key inserts by specifically detecting the duplicate-key error, rather than swallowing all exceptions. Recording the processed marker and updating business data must happen within the same transaction to avoid a “marked but not executed” or “executed but not marked” state.

An idempotency key must represent a stable business action. Do not generate a new UUID each time the consumer receives a message, because upon redelivery a new UUID will make the system treat it as a different task.

If the consumer calls an external service that does not participate in the database transaction, a local transaction alone cannot guarantee a single external effect. In that case, you need an idempotency key supported by the external service, or a reconciliation process.

## 8. Processing Order and Work Partitioning

A queue can preserve message order by arrival order, but multiple consumers processing in parallel mean completion order is no longer guaranteed. For example, `task-1` is delivered first but takes 5 seconds, while `task-2` is delivered later but takes only 100 ms; `task-2` can finish first.

If business logic requires ordering:

- Use a single sequential consumer for the data scope that needs ordering, accepting lower throughput.
- Partition by a business key, such as `orderId`, so messages for the same order go into the same partition/queue.
- Use one sequential consumer per partition if the broker and architecture support it.
- Check a version or sequence number in the database to reject stale updates arriving after newer updates.

Do not enable multiple consumers on a queue and assume operations on the same customer, order, or account will finish in order. Ordering must be designed around business keys and boundaries.

## 9. Backpressure and Scalability

A queue helps absorb traffic spikes for a period of time, but a queue does not create infinite processing capacity. If the producer sends faster than consumers process for a sustained period, queue length will grow.

Measures to consider:

- Set concurrency limits based on the real capacity of the database and downstream services.
- Monitor enqueue/dequeue rates and the age of the oldest message.
- Rate-limit producers or return controlled acceptance status when the system is overloaded.
- Separate queues by task types that have different processing durations or priority levels.
- Set timeouts on external calls and limit retry attempts.
- Use capacity limits or appropriate TTL policies so queues do not consume unbounded resources.
- Scale consumers according to backlog and latency, while avoiding scaling faster than downstream systems can supply connections.

Queue length is not the only metric. You must also inspect ready message count, unacknowledged message count, active consumer count, throughput, processing duration, redelivery rate, and the DLQ. A queue with few ready messages but many unacknowledged messages may still be bottlenecked at the consumers.

## 10. Data Durability and Producer Acknowledgements

A durable queue only preserves the queue definition across broker restarts. To improve message survivability, consider all of the following together:

- Queues/exchanges have appropriate durable settings.
- Messages are marked persistent.
- The broker has publisher confirms enabled so the producer knows the broker has accepted responsibility for the message.
- The producer handles send failures or missing confirmations.
- Consumers ack after business processing has completed.
- Backups, replication, or an appropriate queue type are configured for availability requirements.

Do not equate “the send method did not throw an exception” with “the message was durably saved and is guaranteed to be processed.” Publisher confirms, routing results, and consumer acknowledgements address different stages of the message lifecycle.

With RabbitMQ, you can enable publisher confirms in Spring Boot configuration and use callbacks/returned messages to handle cases where the broker rejects or cannot route a message. Exact configuration depends on the Spring Boot/Spring AMQP version and system topology; check both confirms and mandatory returns rather than relying only on producer logs.

## 11. Transactions, Outbox, and Consistency Boundaries

A common mistake is updating the database and then sending a message as two independent operations:

1. The database commit succeeds.
2. The application crashes before sending the message.

As a result, business data changed but there is no message for workers to process. The reverse can also occur if the message is sent first and then the database transaction rolls back.

The transactional outbox solves this gap by writing the business change and an outbox record within the same database transaction. A separate publisher reads the outbox and sends messages to the broker; once sent successfully, it marks the record as published. The publisher can send duplicates during failures, so consumers still need idempotency.

On the consumer side, if you need to update the database and then ack the broker, understand the transaction manager and commit timing. A database transaction and a RabbitMQ acknowledgement do not automatically become a distributed transaction simply because the listener has `@Transactional`. Design for safe redelivery and use outbox/inbox patterns when consistency across multiple systems is required.

## 12. Observability and Operations

Metrics to monitor:

| Metric | Meaning |
|---|---|
| Ready messages | Number of messages waiting to be delivered to consumers |
| Unacknowledged messages | Number of messages delivered but not yet acked |
| Consumer count | Number of consumers currently registered |
| Publish/ack rate | Sending rate and completion processing rate |
| Oldest message age | How long the oldest message has been waiting |
| Redelivery rate | Frequency of messages being redelivered |
| DLQ depth | Number of quarantined messages |
| Processing latency | Time from when a consumer receives a message until completion |
| Failure rate | Error rate by task type |

Logs should include `messageId`, `taskId`, `correlationId`, task type, attempt count (if available), processing duration, and outcome. Do not log tokens, passwords, sensitive personal data, or the entire payload unnecessarily.

An alert based solely on queue depth can be noisy when the system is processing a normal batch burst. Combine backlog size with message age, processing rate, and business-acceptable completion thresholds.

## 13. Common Design Mistakes

- **Running multiple consumers while expecting every consumer to receive every message**: that is publish/subscribe, which requires separate queues or subscriptions.
- **Acking before business processing completes**: a worker crashing after acking can lose work.
- **Assuming no duplicate messages**: redelivery is normal behavior under at-least-once delivery.
- **Immediate infinite retries**: creates a hot loop, wastes CPU, and hides data errors.
- **Prefetch too large**: one consumer can hold too many unprocessed messages, causing uneven distribution.
- **Increasing concurrency without measuring downstream limits**: can overload databases or external APIs.
- **Assuming a FIFO queue means FIFO completion**: multiple consumers alter completion order.
- **Having no DLQ and no replay process**: failed messages can be lost or clog the queue.
- **Using only a durable queue while ignoring persistent messages and publisher confirms**: insufficient to confirm the producer handed off the message safely.
- **Mechanically coupling a database transaction with a broker ack**: two separate resources do not automatically commit/roll back atomically.

## 14. When Should You Use Competing Consumers?

Use this pattern when there is a stream of work to distribute across multiple workers, each message only needs to be handled by one worker, and asynchronous processing is acceptable. Examples: sending emails, processing files, generating thumbnails, syncing data, running reports, and retryable background jobs.

Consider another model when:

- Every service must receive an event: use publish/subscribe with a separate queue per group.
- Strict ordering by a key is required: use partitioning or sequential processing per key.
- Tasks have different priorities or SLAs: split queues or design appropriate routing/prioritization.
- Tasks are very short and extremely high volume: measure broker overhead, batching, and batch-processing capabilities.
- Tasks require an immediate response: consider synchronous processing or returning a job status for the client to query later.

## 15. Production Readiness Checklist

- [ ] Queues and topology are explicitly declared, with a backward-compatible change process.
- [ ] Producer handles publish failures, publisher confirms, and unroutable messages.
- [ ] Messages have stable identifiers, versioned schemas, and payloads free of unnecessary data.
- [ ] Consumers ack after business processing completes.
- [ ] Handlers are idempotent and tested for redelivery.
- [ ] Retries are bounded, have backoff, and route to a DLQ.
- [ ] Ownership is assigned for inspecting and replaying the DLQ.
- [ ] Concurrency, prefetch, and connection pools are measured under realistic load.
- [ ] Timeouts, rate limits, and backpressure are in place for downstream services.
- [ ] Ready messages, unacknowledged messages, consumer count, latency, redeliveries, and DLQ are monitored.
- [ ] Ordering requirements per business key are clearly defined.
- [ ] A plan exists for handling old messages, old schemas, and rolling out new consumer versions.

## 16. Summary

Competing consumers is the pattern for scaling a work queue horizontally: multiple consumers register on the same queue and share messages. The broker helps distribute the work, but the application still has to decide how to acknowledge, retry, handle duplicates, preserve order, and limit load.

When implementing with Spring AMQP, `@RabbitListener` with `concurrency` creates multiple consumers for the same endpoint; `prefetch` controls how many messages are in flight; acknowledgement determines when the broker considers a message complete. A reliable system combines at-least-once delivery with idempotency, bounded retries, a DLQ, publisher confirms, backlog observability, and transactional design aligned with business needs.