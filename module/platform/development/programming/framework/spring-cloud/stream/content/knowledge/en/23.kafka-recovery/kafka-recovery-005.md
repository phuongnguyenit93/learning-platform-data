# Choosing Error Handling at the Binder or Listener Container

When a Spring Cloud Stream consumer reads messages from Kafka, errors can be handled at two layers. **Binder-level error handling** lets the Kafka Binder apply retries and DLQs according to binding properties. **Listener-container error handling** delegates decisions about retries, backoff, recovery, and offset acknowledgement to Spring Kafka's listener container, typically through a CommonErrorHandler such as DefaultErrorHandler.

Both options aim to handle failed messages, but they sit at different positions along the message path. Choosing the right layer keeps configuration simple for common requirements, or gives deeper control when you need custom retry policies, a DLQ on another cluster, exception classification, or per-attempt tracking.

## 1. Position of the Two Error-Handling Layers

Simplified processing flow:

~~~text
Kafka topic
    |
    v
Kafka consumer / listener container
    |
    v
Kafka Binder
    |
    v
Spring Cloud Stream binding
    |
    v
Function / Consumer
    |
    v
Business processing
~~~

When an imperative handler throws an exception, the error propagates back through the message processing path. The Kafka Binder can apply retry and DLQ according to the binding configuration. In the other option, Spring Kafka's listener container takes responsibility for handling the exception—deciding whether to redeliver the record, skip it after recovery, or send it to a dead-letter topic.

Key differences:

- **Binder-level:** policies are declared via Spring Cloud Stream properties; the binder manages retry/DLQ within its own mechanism. This is usually the first choice for bounded retries and standard DLQs.
- **Listener-container-level:** the application configures CommonErrorHandler, DefaultErrorHandler, recoverer, and BackOff on the listener container. This unlocks advanced Spring Kafka capabilities and per-destination/group customization.

Do not configure both layers to handle the same binding without clearly defining which side owns retries and the DLQ. If both the binder and the container retry, actual attempt counts can differ from expectations, causing extended delays or repeated redeliveries.

## 2. Choosing Binder-Level for Simple Handling Policies

Binder-level fits when the application needs:

- A finite number of attempts with simple backoff.
- Routing failed records to a DLQ on the same Kafka cluster.
- A fairly uniform policy across one or a few bindings.
- Minimal coupling to Kafka consumer internals.
- Readable configuration managed alongside application.yml.

Example consumer processing order events:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderCreated(String orderId, String customerId) {}

interface OrderService {
    void process(OrderCreated order);
}

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService orderService) {
        return orderService::process;
    }
}
~~~

Binding, retry, and DLQ configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.order-processor.dlq
~~~

In this configuration, max-attempts of 4 allows up to four handler invocations, including the initial delivery. Backoff starts at 1 second, multiplies by 2, and is capped at 10 seconds. Once attempts are exhausted and the error persists, the binder routes the record to the specified DLQ.

The Kafka Binder requires an explicit consumer group to enable DLQ. Anonymous consumers cannot enable this feature. If dlq-name is omitted, the binder uses a default name in the form error.<destination>.<group>. Failed records are sent to the DLQ along with source metadata and exception information supported by the binder.

## 3. How the Binder Executes Retries and DLQ

With the Kafka Binder, when retry and enable-dlq are configured on a consumer binding, these operations run inside the binder by default, without requiring the listener container or Kafka consumer to directly drive retries. Conceptually:

~~~text
Receive record
    |
    v
Invoke Function / Consumer
    |
    +---- succeeded -------------------> continue
    |
    v
Handler throws exception
    |
    v
Binder retries per max-attempts / backoff
    |
    +---- later attempt succeeded -----> continue
    |
    v
Attempts exhausted
    |
    v
Send record to DLQ
~~~

Binder-level saves developers from having to set up DefaultErrorHandler for common scenarios. However, it does not expose every customization capability of the listener container. When decisions must depend on record, exception, partition, or consumer state, consider moving to container-level.

One Kafka Binder-specific detail to remember: if DLQ is not enabled, max-attempts does not govern retries in the binder-level way it does when DLQ is enabled. In that case, retries may fall back to Spring Kafka's listener container default. Current Kafka Binder documentation describes the container default as ten retry attempts. Thus, setting max-attempts to 1 on a binding without enabling DLQ does not mean retries are completely disabled. To change that policy, configure the container's error handler.

## 4. When Should Retry/DLQ Move to the Listener Container?

Listener-container-level is better suited in these situations:

| Requirement | Why container-level fits |
|---|---|
| Total retry/backoff duration may exceed max.poll.interval.ms | Can use listener container backoff/pause mechanisms to control consumer liveness and rebalancing |
| Sending dead letters to another Kafka cluster | Can configure a dedicated KafkaTemplate/recoverer for the target cluster |
| Need RetryListener or per-attempt callbacks | Spring Kafka error handlers provide deep hooks |
| Complex exception classification | DefaultErrorHandler lets you distinguish retryable and non-retryable errors |
| Need recovery logic by record, partition, or offset | Recoverer has access to ConsumerRecord |
| Need custom seek, commit, or offset acknowledgement | Listener container manages consumer lifecycle and acknowledgement |
| Using batch listeners | Internal binder retry does not support batch mode; requires container-level handling or appropriate acknowledgement |

If the policy is simply "retry a few times then send to a DLQ in the same cluster," binder-level is usually enough. If requirements touch consumer behavior, offsets, poll intervals, or target clusters, container-level is usually better.

## 5. CommonErrorHandler and DefaultErrorHandler

Spring Kafka provides CommonErrorHandler as the unified interface for handling errors in record listeners and batch listeners. DefaultErrorHandler is a common implementation supporting:

- Backoff between redeliveries.
- Calling a recoverer when attempts are exhausted.
- Classifying exceptions as retryable or non-retryable.
- Handling the failed record and remaining records in a batch per container semantics.
- Adjusting how seeks occur or retaining records for redelivery.

Starting with Spring Kafka 2.8, CommonErrorHandler replaces older APIs such as SeekToCurrentErrorHandler. When writing new code, use DefaultErrorHandler and verify compatibility with the Spring Kafka version managed by Spring Cloud Stream.

Example creating a handler with retry and recoverer:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class KafkaErrorHandlerConfiguration {

    @Bean
    CommonErrorHandler orderErrorHandler(KafkaTemplate<Object, Object> template) {
        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        template,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".dlq",
                                record.partition()));

        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1000L, 2L));
    }
}
~~~

FixedBackOff with 1000 ms and 2 retries waits 1 second between attempts, allowing up to three processing attempts including the initial one. Once retries are exhausted, DeadLetterPublishingRecoverer sends the record to a topic suffixed with .dlq, preserving the corresponding partition ID. The DLQ topic must already exist or be provisioned per system policy and must have enough partitions to accept the selected partition ID.

This example illustrates CommonErrorHandler and the recoverer; KafkaTemplate must be configured with serializers suitable for the actual key/value types. If using native decoding or binary payloads, ensure the template can publish failed records in the right format.

## 6. Attaching the Handler to the Right Listener Container

You can use ListenerContainerCustomizer to customize a container after the binder has created it and applied basic configuration:

~~~java
import org.springframework.cloud.stream.config.ListenerContainerCustomizer;
import org.springframework.kafka.listener.AbstractMessageListenerContainer;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderContainerConfiguration {

    @Bean
    ListenerContainerCustomizer<AbstractMessageListenerContainer<?, ?>>
    orderContainerCustomizer(CommonErrorHandler orderErrorHandler) {

        return (container, destinationName, group) -> {
            if ("orders.created".equals(destinationName)
                    && "order-processor".equals(group)) {
                container.setCommonErrorHandler(orderErrorHandler);
            }
        };
    }
}
~~~

The customizer receives the destination name and group, so you can apply the handler only to the required binding. Avoid attaching a specialized handler to every container if bindings have different policies.

In current Kafka Binder versions, you can use the common-error-handler-bean-name property per consumer binding to select a CommonErrorHandler bean by name:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              common-error-handler-bean-name: orderErrorHandler
~~~

When this property is set, the application-provided handler takes precedence over other error handlers defined by the binder. This is a concise option when you only need to attach a CommonErrorHandler bean to a specific binding. That handler must then take full responsibility for the retries, recovery, and DLQ behavior the application needs.

If you only use a generic ListenerContainerCustomizer to set a handler while leaving enable-dlq enabled on the binder, the binder may still retain control of retry/DLQ per its configuration. If the goal is to move both retry and DLQ to the container while still reusing the retry metadata and DLQ resolver created from the binding, use ListenerContainerWithDlqAndRetryCustomizer and return false from retryAndDlqInBinding() for the corresponding binding.

## 7. Moving Both Retry and DLQ from Binder to Container

If you want to keep retry/backoff/DLQ configuration on the binding while executing it in the listener container, the Kafka Binder provides ListenerContainerWithDlqAndRetryCustomizer. This customizer receives:

- The listener container created for the binding.
- The destination name and consumer group.
- A function determining the target DLQ topic/partition, if DLQ is enabled.
- A BackOff built from the binding's retry properties.

Crucially, retryAndDlqInBinding() must return false for any binding moved to the container. If it still returns true, the binder continues owning retry/DLQ inside the binding.

~~~java
import org.springframework.cloud.stream.binder.kafka.ListenerContainerWithDlqAndRetryCustomizer;
import java.util.function.BiFunction;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.AbstractMessageListenerContainer;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.BackOff;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderRetryContainerConfiguration {

    @Bean
    ListenerContainerWithDlqAndRetryCustomizer orderRetryCustomizer(
            KafkaTemplate<?, ?> template) {

        return new ListenerContainerWithDlqAndRetryCustomizer() {

            @Override
            public void configure(
                    AbstractMessageListenerContainer<?, ?> container,
                    String destinationName,
                    String group,
                    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>
                            dlqDestinationResolver,
                    BackOff backOff) {

                if ("orders.created".equals(destinationName)
                        && "order-processor".equals(group)) {

                    ConsumerRecordRecoverer recoverer =
                            new DeadLetterPublishingRecoverer(
                                    template,
                                    dlqDestinationResolver);

                    container.setCommonErrorHandler(
                            new DefaultErrorHandler(recoverer, backOff));
                }
            }

            @Override
            public boolean retryAndDlqInBinding(
                    String destinationName,
                    String group) {

                return !("orders.created".equals(destinationName)
                        && "order-processor".equals(group));
            }
        };
    }
}
~~~

At the same time, declare retry and DLQ on the binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 30000
            back-off-multiplier: 2
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.order-processor.dlq
~~~

With this approach, the binder constructs the BackOff and DLQ destination resolver from the binding properties and passes them to the customizer. DefaultErrorHandler in the listener container uses those objects to run retries and recovery. As a result, retry settings remain centralized in application.yml while execution is delegated to Spring Kafka.

If configure() receives null for the DLQ resolver or backoff, verify that the binding has enabled DLQ and declared retry properties properly before creating the handler. Only use this customizer for bindings whose DLQ/retry policy is designed accordingly.

If the application configures multiple named binders, wiring the customizer into the Kafka binder may require a BinderCustomizer to attach it directly to KafkaMessageChannelBinder. Check the documentation for your version and verify the customizer is actually invoked for the right binder.

## 8. Why Does Total Retry Time Relate to max.poll.interval.ms?

A Kafka consumer must continue polling the broker within max.poll.interval.ms. If a consumer fails to poll for too long, the group coordinator may consider it dead and initiate a partition rebalance.

Suppose a message takes four attempts, each with a 20-second backoff, plus business processing time. Total processing time could exceed the poll limit. In that case, the partition could be revoked and assigned to another consumer while the application is still waiting on retries.

When retries are long, you should:

- Compute total processing plus backoff time and compare it against max.poll.interval.ms.
- Use listener-container-level if you need pause/resume control and long backoffs.
- Consider Spring Kafka's ContainerPausingBackOffHandler when wait durations exceed the poll cycle.
- Adjust max.poll.interval.ms only after evaluating processing duration and rebalance impact.
- Monitor rebalances, consumer lag, and actual retry counts.

Do not raise max.poll.interval.ms arbitrarily to mask an overly slow consumer. If a message can take several minutes to complete, consider moving long-running work to an asynchronous workflow and acknowledging the message only after the work is durably persisted.

## 9. Exception Classification and Retry Decisions

Not every error can be resolved by retrying. DefaultErrorHandler allows adding exceptions to the non-retryable group:

The following example assumes the application has registered a ConsumerRecordRecoverer bean to route records with exhausted retries to the DLQ:

~~~java
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderExceptionClassificationConfiguration {

@Bean
DefaultErrorHandler orderDefaultErrorHandler(
        ConsumerRecordRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L));

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            UnsupportedOperationException.class);

    return handler;
}
}
~~~

This example treats IllegalArgumentException and UnsupportedOperationException as errors that should not be retried. Choose exceptions based on your business contract:

| Error type | Example | Typically suitable policy |
|---|---|---|
| Transient error | Timeout, intermittent DB connectivity | Retry with backoff and cap |
| Data error | Payload missing required field | Do not retry; recover data or DLQ |
| Contract/schema error | Unsupported version | Do not retry until schema/consumer is fixed |
| Programming bug | Wrong mapping, NullPointerException | Alert, fix code; avoid futile retries |
| External dependency error | Partner API temporarily down | Retry within time budget and rate limit |

DefaultErrorHandler has default exceptions treated as fatal—such as deserialization errors, message conversion errors, or class cast errors; these are typically sent straight to the recoverer instead of retrying multiple times. Classification can be adjusted, though carefully: retrying an undecodable payload will not make the data valid.

## 10. Deserialization Errors Occur Before the Function

Some errors happen before the message is converted into a Spring Message<?> and passed to the Function. For example, the Kafka consumer cannot deserialize the value or key. In that case, the business handler never receives a converted payload to inspect.

With Kafka, ErrorHandlingDeserializer can be used to retain deserialization error details in headers and allow Spring Kafka's error handler/recoverer to handle the failed record. Specific configuration depends on your application's serializers/deserializers:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                key.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
                spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

This example illustrates the delegate structure; JsonDeserializer needs target type/trusted packages configured for your application. Do not copy this exact configuration if the consumer uses Avro, Protobuf, or another native deserializer. When handling poison pills, test that the recoverer can publish the original record to the DLQ and retain enough metadata.

## 11. Batch Listeners and Binder Retry Limits

The Kafka Binder supports batch mode so a Function receives a list of records from a single poll. However, internal binder retry does not support batch mode; max-attempts may be forced to 1. If batch retries are needed, you must use container-level mechanisms such as DefaultErrorHandler with batch semantics or appropriate manual acknowledgement.

In a batch listener, you need to know which record in the batch failed. Spring Kafka provides BatchListenerFailedException to indicate the failing record/index in the batch, allowing the container to commit processed records and redeliver the remainder per configuration. If using manual AckMode, you can use Acknowledgment.nack(index, sleep) to specify the slice of the batch to redeliver. Verify these APIs and semantics against your Spring Kafka version.

Do not assume batch retry works identically to record retry. An error on one record can cause part of the batch or the entire batch to be reprocessed, depending on the handler and how the listener reports the error.

## 12. Kafka Transactions Change How Retry and DLQ Work

When the Kafka Binder enables transactions, retry and dead-lettering do not work like the standard binder retry path. If retries happen inside the original transaction, an exception can roll back the transaction and roll back any DLQ records published inside that transaction as well.

With a transactional binder, retry properties are used to configure DefaultAfterRollbackProcessor on the listener container. Dead-letter publishing is also deferred to the post-rollback phase. Therefore:

- Do not blindly apply binder-level retry/DLQ examples to a transactional binder.
- Clearly identify the transaction manager and transaction boundaries.
- Verify that offsets are committed when a record is recovered.
- Test transaction rollback, recoverer failure, and broker restart scenarios.
- Ensure transactional IDs and transaction settings are properly configured across producer/consumer instances.

If you need to synchronize database writes with Kafka, understand clearly which system each transaction covers. A Kafka transaction does not automatically make an external database transaction atomic.

## 13. Reactive Functions Have Their Own Error-Handling Mechanism

RetryTemplate and imperative retry/DLQ properties apply to imperative message handlers such as Consumer<T> or Function<T, R>. Reactive functions accepting and returning Flux do not handle individual messages in the same way; the framework wires their publishers to the input stream.

For reactive functions, use Reactor operators:

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

record OrderEvent(String orderId, String status) {}

record OrderResult(String orderId, String status) {}

interface ReactiveOrderService {
    Mono<OrderResult> processReactive(OrderEvent event);
}

@Configuration
class ReactiveOrderConfiguration {

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderResult>> processOrdersReactive(
            ReactiveOrderService orderService) {

        return events -> events.concatMap(event ->
                orderService.processReactive(event)
                        .retryWhen(Retry.backoff(
                                3,
                                Duration.ofSeconds(1))
                                .maxBackoff(Duration.ofSeconds(10))));
    }
}
~~~

This example uses concatMap to process events sequentially within the publisher; retry is applied to the per-event publisher. If concurrency is desired, consider flatMap, but evaluate ordering and concurrency limits. Design a dedicated way to route failed events to a DLQ or error stream; do not assume imperative handler settings like enable-dlq and max-attempts apply automatically to reactive pipelines.

## 14. ErrorMessage Handlers Are Not Listener-Container Handlers

Spring Cloud Stream allows declaring a Consumer<ErrorMessage> to receive errors at the function binding level:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.support.ErrorMessage;

@Bean
Consumer<ErrorMessage> orderErrorMessages() {
    return errorMessage -> {
        // Record audit or emit alerts per application policy.
    };
}
~~~

You can attach the handler using the binding's error-handler-definition property. However, Spring Cloud Stream's custom ErrorMessage handler is a separate mechanism and excludes the default framework/binder error handlers for that binding. When this handler is declared, sending failed messages to the DLQ via the binder mechanism will not operate as before, even if DLQ is configured.

Example attaching the handler to a binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          error-handler-definition: orderErrorMessages
~~~

Therefore, do not confuse three concepts:

- Consumer<ErrorMessage>: handler at the Spring Cloud Stream binding level.
- CommonErrorHandler/DefaultErrorHandler: handler at the Spring Kafka listener container level.
- Binder retry/DLQ properties: error-handling policy managed by the Kafka Binder.

Choose one primary mechanism per binding, then add logging/metrics in a way that preserves the chosen recovery path.

## 15. Observing Retry and Container Behavior

After deployment, monitor:

- Average retry counts and backoff duration distribution.
- Number of records entering the DLQ by topic, group, and exception type.
- Age of the oldest record in the DLQ.
- Consumer lag and per-record processing duration.
- Rebalance count and signs of exceeding max.poll.interval.ms.
- Recovery success rate and failures while publishing to the DLQ.
- Counts of deserialization errors, conversion errors, and business errors.

Logs should include topic, partition, offset, key/event ID, consumer group, binding, exception class, and attempt number. Do not log full payloads if they contain sensitive data. When a container-level handler recovers a record, log clearly whether DLQ publishing succeeded or the recoverer failed.

## 16. Testing Error-Handling Policies

Tests should verify both where retries execute and the final outcome:

1. Handler fails on the first attempt but succeeds on the next; verify call count and backoff timing.
2. Handler fails until retries are exhausted; verify the record goes to the right DLQ.
3. Non-retryable exception; verify the recoverer is called immediately per classification.
4. DLQ disabled; verify actual container policy instead of assuming from max-attempts alone.
5. Container-level customizer applies only to the intended destination/group.
6. When retryAndDlqInBinding returns false, verify the binder does not simultaneously run retry/DLQ.
7. Simulate long retries to observe max.poll.interval.ms and rebalancing.
8. Simulate deserialization errors before the Function runs.
9. Test batch mode, transactional binder, and reactive functions under their respective mechanisms.
10. Simulate DLQ publish failures to ensure records are not silently lost.

The Test Binder can test Function logic and some wiring, but it does not replace integration tests for DefaultErrorHandler, Kafka offsets, consumer rebalances, native deserialization, and DLQ topics. Use a real Kafka broker or equivalent test environment for listener-container guarantees.

## 17. Decision Table

| Criterion | Binder-level | Listener-container-level |
|---|---|---|
| Simple finite retry | Suitable | Usable, but more configuration |
| Same-cluster DLQ with standard naming | Suitable | Supports deeper customization |
| Needs custom recoverer | More limited | Suitable |
| Needs DLQ on another cluster | Inconvenient | Suitable with dedicated KafkaTemplate |
| Long retries affecting poll interval | Consider moving to container | Can use container backoff/pause |
| Retry listener or complex classification | Limited | Suitable |
| Batch listener | Not supported by binder retry | Use matching handler/acknowledgement |
| Transactional binder | Requires post-rollback semantics | Use container/AfterRollbackProcessor mechanism |
| Reactive Function | Imperative RetryTemplate/DLQ does not apply | Use Reactor operators and dedicated error stream |

## 18. Pre-Release Checklist

- Identified whether the binding uses an imperative or reactive function.
- Chosen a single layer owning retry and DLQ for each binding.
- If using binder-level DLQ, set an explicit consumer group and enabled enable-dlq.
- Understood that max-attempts includes the initial delivery and checked behavior when DLQ is disabled.
- Chosen backoff aligned with dependency recovery times.
- If moving to container, configured CommonErrorHandler and the appropriate customizer.
- With ListenerContainerWithDlqAndRetryCustomizer, returned false for retryAndDlqInBinding() on migrated bindings.
- Checked total retry duration against max.poll.interval.ms.
- Classified retryable and non-retryable exceptions.
- Tested deserialization errors, batch mode, and transactional binder if used by the application.
- Monitored lag, rebalances, DLQ, and recoverer errors after deployment.

Binder-level is a good fit for common retries and DLQs declared concisely on the binding. Listener-container-level is right when the application needs deeper control over how Spring Kafka redelivers records, backoffs, recoverers, offsets, or DLQ destinations. With the Kafka Binder, you can move retry/DLQ from the binder to the container via ListenerContainerWithDlqAndRetryCustomizer while retaining retry metadata from the binding. Decide clearly on one responsible layer per binding and test against real Kafka to verify retry, acknowledgement, rebalance, and DLQ behavior.

## References

- [Spring Cloud Stream — Kafka Binder: Retry and Dead Letter Processing](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/overview.html)
- [Spring Cloud Stream — Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html)
- [Spring Cloud Stream — General Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
