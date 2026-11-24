# Exception changing between retries

In Spring Kafka, the same record can fail with different exception types across redelivery attempts. For instance, the listener may hit a temporary database access error on the first attempt, a service timeout on the next, and an exception wrapped in another exception on a subsequent attempt. This change can affect how the error handler classifies the error, chooses retry vs. recovery, and continues or restarts the backoff sequence.

When using blocking retries with **DefaultErrorHandler**, Spring Kafka tracks the record's failure state and uses **BackOff** to decide when to redeliver. The **resetStateOnExceptionChange** property controls whether backoff state resets when the exception type changes. Understanding this behavior avoids retrying too long, recovering prematurely, or mishandling non-retryable errors.

## 1. Why can exceptions change between retries?

Retrying does not guarantee the next processing attempt will encounter the exact same exception as before. Each time the listener is re-invoked, code runs under a different system state:

- A database may shift from connection failures to lock or timeout errors.
- A REST API may return a timeout on the first call and a rate-limit error on the next.
- One downstream service may recover, while a later step inside the listener fails.
- A business exception may be wrapped by a framework or adapter exception.
- External data or state may change between redeliveries.

Example:

~~~text
Record: orders-2, offset 105

Initial attempt:
  Listener -> TransientDataAccessException

Retry 1:
  Listener -> SocketTimeoutException

Retry 2:
  Listener -> TransientDataAccessException

Retry 3:
  Listener -> processing succeeds
~~~

Different exceptions can signal different severity levels. A temporary connection error can be retried, whereas an invalid data error may never resolve on its own. Thus, the error handler must evaluate both the current exception type and accumulated retry state.

## 2. How does Spring Kafka track retry state?

With blocking retries, **DefaultErrorHandler** handles failures after the listener fails. The handler uses **BackOff** to determine wait intervals between attempts and tracks failure progress per record.

The flow can be visualized as:

~~~text
Consumer polls record
       |
       v
Listener processes record
       |
       +------ Success ----------> continue processing
       |
       v
Listener throws exception
       |
       v
DefaultErrorHandler
       |
       v
Classify exception
       |
       +------ Non-retryable ----> Recovery / DLT
       |
       v
Get next step from BackOff
       |
       +------ Retries remain ---> redeliver record
       |
       v
BackOff exhausted
       |
       v
Recovery / DLT
~~~

Retry state is tracked per failed record, tied to the record's coordinates in the partition, such as topic, partition, and offset. Therefore, a record's backoff state must not be mistaken for a shared counter across the entire consumer group.

On the next failure, the handler can compare the current exception against the previous failure's exception. If the exception type changes and **resetStateOnExceptionChange** is enabled, the record's backoff state resets to start the backoff sequence anew. If reset is disabled, the handler continues the current backoff sequence unless the new exception is classified as non-retryable or another recovery condition applies.

**DefaultErrorHandler** retry state is held in-memory inside the consumer process. After an application restart, uncommitted records can be re-read and in-memory retry state is recreated from scratch. If persistent retry history across restarts is required, the application needs a separate state store or an appropriate retry architecture.

## 3. What does resetStateOnExceptionChange control?

**resetStateOnExceptionChange** is a property on Spring Kafka's record-failure handling layer. It determines whether to restart the **BackOff** state when the exception class changes across failures of the same record.

| Setting | When exception class changes | Effect |
|---|---|---|
| false | Keep current backoff progress | Retry count and wait intervals continue along the sequence already started. |
| true | Reset the record's backoff state | The backoff sequence restarts from step one for the new exception class. |

For example, with **FixedBackOff(1000L, 2L)**: the backoff sequence has two retries, one second apart. If the exception class changes and reset is enabled, the backoff counter restarts under this policy. If reset is disabled, the next failure continues the current progression.

Set this property explicitly rather than relying on an unverified default. Default values and configurability may depend on the Spring Kafka version; check the API of the version in use.

### When to keep backoff state

Choose not to reset when you want to cap total retries across a record's failure streak, even if exceptions change. This prevents alternating exceptions from resetting the backoff counter back to the start repeatedly.

Example:

~~~text
FixedBackOff: 1 second, max 3 retries

Failure 1: TimeoutException
  -> wait 1 second
Failure 2: TransientDataAccessException
  -> wait 1 second
Failure 3: SocketTimeoutException
  -> wait 1 second
Failure 4: TimeoutException
  -> retries exhausted, invoke recoverer
~~~

This example illustrates the backoff sequence continuing even as the exception class changes. If a new exception belongs to the non-retryable group, classification can move the record to recovery earlier.

### When to reset backoff state

Choose reset when each new exception type represents a distinct failure phase and the application wants to grant that error type its own retry sequence.

~~~text
FixedBackOff: 1 second, max 3 retries

Failure 1: TimeoutException
  -> start backoff sequence
Failure 2: TimeoutException
  -> continue current sequence
Failure 3: TransientDataAccessException
  -> exception class changed, reset backoff
  -> restart from step one
Failure 4: TransientDataAccessException
  -> continue new sequence
~~~

Resetting is useful if a new exception class reflects a different recovery condition. However, if exceptions fluctuate continuously, the retry sequence can restart repeatedly and prolong record processing time. Therefore, enforce an overall time limit, monitor retry counts, and define clear recovery.

## 4. Exception classification still decides retry vs. recovery

Resetting backoff and classifying exceptions are two distinct decisions:

- **Classification** decides whether an exception is retried or recovered immediately.
- **BackOff state** decides how long to wait if retrying and how many steps remain in the current sequence.
- **Recovery** decides what to do when no longer retrying, such as publishing the record to a dead-letter topic.

**DefaultErrorHandler** has a default list of exceptions treated as fatal/non-retryable, such as errors related to deserialization, message conversion, method argument resolution, missing methods, and class casts. Data or configuration errors usually do not clear on waiting, so retrying may not help.

Custom classifications can be added:

~~~java
DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 3L));

errorHandler.addNotRetryableExceptions(
        IllegalArgumentException.class,
        InvalidOrderException.class);

errorHandler.addRetryableExceptions(
        TransientDataAccessException.class,
        DownstreamTimeoutException.class);
~~~

This code illustrates configuring retryable and non-retryable exceptions. Import your application's real exceptions and verify the API for your Spring Kafka version.

If the exception class changes from a retryable error to a non-retryable error, the error handler can move directly to recovery per classification. Enabling **resetStateOnExceptionChange** does not turn a non-retryable exception into a retryable one and does not override classification rules.

Conversely, if the exception class changes from non-retryable to retryable, the actual decision depends on the exception thrown on the current delivery and classifier rules. Do not assume a previous exception's state dictates all subsequent retries.

## 5. Configuring DefaultErrorHandler in Spring Kafka

The example below configures blocking retry, dead-letter recovery, error classification, and resetting backoff when the exception class changes:

~~~java
@Configuration
public class KafkaErrorHandlingConfiguration {

    @Bean
    public DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        FixedBackOff backOff = new FixedBackOff(1_000L, 3L);

        DefaultErrorHandler errorHandler =
                new DefaultErrorHandler(recoverer, backOff);

        errorHandler.addNotRetryableExceptions(
                IllegalArgumentException.class,
                InvalidOrderException.class);

        errorHandler.addRetryableExceptions(
                TransientDataAccessException.class,
                SocketTimeoutException.class);

        errorHandler.setResetStateOnExceptionChange(true);

        return errorHandler;
    }
}
~~~

Registering the handler on the listener container factory:

~~~java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        kafkaListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory,
                DefaultErrorHandler kafkaErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(kafkaErrorHandler);
    return factory;
}
~~~

In this example:

- **FixedBackOff(1_000L, 3L)** defines a one-second interval and at most three retries within one backoff sequence.
- **addNotRetryableExceptions()** marks data/business errors that should not be retried.
- **addRetryableExceptions()** adds recoverable infrastructure errors.
- **setResetStateOnExceptionChange(true)** restarts the backoff sequence if the exception class for the same record changes.
- **DeadLetterPublishingRecoverer** is the recovery callback sending unprocessable records to a dead-letter topic per the recoverer's routing rules.

The **KafkaTemplate** type must match the application's key/value serializers and configuration. The example uses **KafkaTemplate<Object, Object>** for illustration; do not copy this exact type if your project's producer factory uses a different type.

To continue backoff when the exception class changes, set:

~~~java
errorHandler.setResetStateOnExceptionChange(false);
~~~

Document this choice explicitly in configuration because it affects how long a record can stay in the retry loop.

## 6. Wrapper exceptions and cause chains

A common source of confusion is that the outer exception may change even when the root cause is virtually identical. Frameworks, serializers, converters, or adapters may wrap the root exception in another exception.

Example:

~~~text
Attempt 1:
  ListenerExecutionFailedException
      caused by SocketTimeoutException

Attempt 2:
  ListenerExecutionFailedException
      caused by ResourceAccessException
          caused by SocketTimeoutException
~~~

Here the outer exception remains **ListenerExecutionFailedException**, yet the cause chain changed. In other cases, the outer exception can shift from one wrapper to another while the root cause stays a timeout.

When investigating, record:

- Outermost exception class.
- Root cause or cause chain.
- Record topic, partition, and offset.
- Current delivery attempt.
- Time elapsed since the prior failure.
- Listener and dependency being executed.

Do not rely solely on exception messages or strings to decide retries. Message text can change across library versions, locales, or requests. Classify by exception type and error semantics; if wrappers are unstable, normalize exceptions at adapter boundaries or configure classifiers to align with the cause chain.

Class-based classification must be verified against how your Spring Kafka version traverses the cause chain. If the application uses multiple wrappers, test scenarios where the wrapper changes while the root cause remains constant to see which exception layer the classifier and **resetStateOnExceptionChange** inspect.

## 7. Designing an exception hierarchy for retries

A system with many error types should have an exception hierarchy that clearly expresses recoverability:

~~~text
ApplicationException
  |
  +-- RetryableApplicationException
  |      |
  |      +-- TemporaryDatabaseException
  |      +-- DownstreamTimeoutException
  |      +-- TemporaryRateLimitException
  |
  +-- NonRetryableApplicationException
         |
         +-- InvalidOrderException
         +-- UnsupportedEventVersionException
         +-- BusinessRuleViolationException
~~~

Example:

~~~java
public abstract class RetryableApplicationException
        extends RuntimeException {

    protected RetryableApplicationException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

public class DownstreamTimeoutException
        extends RetryableApplicationException {

    public DownstreamTimeoutException(
            String message, Throwable cause) {
        super(message, cause);
    }
}

public abstract class NonRetryableApplicationException
        extends RuntimeException {

    protected NonRetryableApplicationException(String message) {
        super(message);
    }
}

public class InvalidOrderException
        extends NonRetryableApplicationException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Listeners or adapters should translate library errors into application exceptions at appropriate boundaries:

~~~java
public void process(OrderEvent event) {
    try {
        paymentClient.authorize(event);
    }
    catch (SocketTimeoutException ex) {
        throw new DownstreamTimeoutException(
                "Payment authorization timed out", ex);
    }
}
~~~

Normalizing exceptions keeps the error handler from coupling tightly to internal HTTP or database library classes. However, do not wrap all errors into a single generic retryable exception. If data or business errors get wrapped as temporary errors, the system can waste retries and grow backlogs.

## 8. Backoff, retry counts, and repeated reset risk

Backoff determines the wait interval between redeliveries. Spring Kafka supports Spring Framework implementations such as **FixedBackOff** and exponential backoff strategies.

Exponential backoff example:

~~~java
ExponentialBackOffWithMaxRetries backOff =
        new ExponentialBackOffWithMaxRetries(5);
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(10_000L);

DefaultErrorHandler errorHandler =
        new DefaultErrorHandler(recoverer, backOff);
~~~

Increasing wait intervals helps avoid hammering a failing dependency. **maxInterval** caps the wait per retry, while the retry count caps the length of one backoff sequence.

When **resetStateOnExceptionChange=true**, each time the exception class changes, the backoff sequence can restart. If errors alternate across multiple classes:

~~~text
TimeoutException
  -> retry
ResourceAccessException
  -> reset, retry
DataAccessException
  -> reset, retry
TimeoutException
  -> reset, retry
~~~

A finite backoff sequence can be restarted multiple times if exception classes keep changing. Therefore, do not rely solely on one sequence's retry count to bound total record processing time when reset is enabled. Add an overall time limit, monitor delivery attempts, and ensure eventual recovery or manual handling.

If business requirements dictate that a record may only retry for a fixed duration, choose a time-bounded policy or store a durable retry deadline. A separate control layer may be needed if exception-driven backoff resets exceed business time limits.

## 9. Retry listeners and observing changing exceptions

When exceptions change between retries, logs stating merely "listener failed" are insufficient. You need visibility into record identity, delivery attempts, and exception types to understand why backoff continued or reset.

Spring Kafka provides **RetryListener** to receive notifications on failed deliveries, successful recoveries, and failed recoveries. Example:

~~~java
errorHandler.setRetryListeners(new RetryListener() {
    @Override
    public void failedDelivery(
            ConsumerRecord<?, ?> record,
            Exception exception,
            int deliveryAttempt) {

        log.warn(
                "Kafka delivery failed: topic={}, partition={}, offset={}, " +
                "attempt={}, exception={}",
                record.topic(),
                record.partition(),
                record.offset(),
                deliveryAttempt,
                exception.getClass().getName());
    }

    @Override
    public void recovered(
            ConsumerRecord<?, ?> record,
            Exception exception) {

        log.info(
                "Kafka record recovered: topic={}, partition={}, offset={}, exception={}",
                record.topic(),
                record.partition(),
                record.offset(),
                exception.getClass().getName());
    }
});
~~~

Callbacks and method signatures may differ across Spring Kafka versions. Use the interface matching your project's dependency version.

Collect the following details:

- Number of delivery attempts per record.
- Exception class and root cause.
- How often the exception class changed.
- How often backoff reset, if observable by the application.
- Total duration from initial failure to recovery.
- Number of records published to DLT.
- Number of failed recoveries.

Do not use topic, partition, and offset as high-cardinality metric labels. Those belong in logs or traces; metrics should use bounded-value labels such as listener ID, exception category, and outcome.

## 10. Recovery and dead-letter topics

Once retries are exhausted or an exception is classified as non-retryable, **DefaultErrorHandler** invokes the recoverer. The recoverer may skip the record per policy, log it, or publish it to a dead-letter topic (DLT).

**DeadLetterPublishingRecoverer** is commonly used to send failed records to a destination topic. The default convention typically appends a DLT suffix and preserves the corresponding partition when the destination topic has enough partitions. In production, explicitly configure routing, serializers, write permissions, and DLT partition counts.

Recovery must be observed as a separate step. Exhausting handler retries does not mean the record was safely handled. If DLT publishing fails, the application needs a policy for recovery failures. Spring Kafka provides **resetStateOnRecoveryFailure** to control backoff state when recovery fails; this is a separate decision from **resetStateOnExceptionChange**.

Do not conflate:

- Exception class changing between processing attempts.
- Recovery callback throwing an exception.
- Record successfully publishing to the DLT.

These three events have different impacts on retry state and final outcomes. Log and track them separately to avoid falsely reporting a record as recovered when DLT publishing actually failed.

## 11. Blocking retry vs. non-blocking retry

**resetStateOnExceptionChange** applies to the backoff state of blocking retry mechanisms in error handlers like **DefaultErrorHandler**.

With non-blocking retry using **@RetryableTopic**, failed records are forwarded to retry topics according to configured delays and attempt counts. This flow creates dedicated retry topics, and each re-consumption is a pass of the record through the retry topology. Do not assume **resetStateOnExceptionChange** governs retry-topic schedules in the same way as **DefaultErrorHandler**.

Example:

~~~java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(
                delay = 1_000,
                multiplier = 2.0,
                maxDelay = 10_000))
@KafkaListener(
        topics = "orders",
        groupId = "orders-service")
public void handle(OrderEvent event) {
    orderService.process(event);
}
~~~

Non-blocking retry fits when you do not want a single failing record to block a partition for long and can accept retried records being handled on a separate topology. However, it affects ordering: newer records on the main topic can be processed before an earlier record finishes in retry topics. If business rules require strict ordering, consider blocking retries or redesigning the processing flow.

Choose one retry model matching ordering, throughput, and operational requirements. Do not stack multiple overlapping retry mechanisms without understanding total attempt counts and maximum record lifetime.

## 12. Testing changing exceptions between retries

Test error handler behavior with the same record and different exception classes. You can use a listener simulating failure counts:

~~~java
AtomicInteger attempts = new AtomicInteger();

@KafkaListener(topics = "orders", groupId = "orders-test")
public void handle(OrderEvent event) {
    int attempt = attempts.incrementAndGet();

    if (attempt == 1) {
        throw new DownstreamTimeoutException(
                "first attempt", new SocketTimeoutException("timeout"));
    }
    if (attempt == 2) {
        throw new TransientDataAccessException("second attempt") { };
    }

    process(event);
}
~~~

This snippet illustrates listener behavior; in real tests, isolate counters per event ID rather than using a single global **AtomicInteger** if multiple records are processed concurrently.

Scenarios to test:

1. Same exception class on every retry: backoff continues along the sequence.
2. Exception class changes, reset disabled: backoff continues along the old sequence.
3. Exception class changes, reset enabled: backoff restarts per policy.
4. Exception changes to a non-retryable type: handler moves to recovery per classification.
5. Exception wrapped in another wrapper: verify classifier handles the cause chain per configuration.
6. Recovery callback fails: test recovery reset policy and redelivery behavior.
7. Application restarts between retries: verify the record is re-read and in-memory retry state is recreated.
8. Alternating exception classes: verify overall time limits and recovery counts.

To test backoff timings, use a **BackOff** with short intervals in tests or spy on the recoverer and retry listener. Avoid long sleeps in tests; use synchronization primitives and bounded timeouts for stable tests.

## 13. Common misconceptions

**When the exception class changes, Spring Kafka always restarts retries.** Do not assume that. Behavior depends on **resetStateOnExceptionChange** and the Spring Kafka version. Configure explicitly and test.

**Resetting backoff makes the new exception retryable.** False. Classification still determines whether the error is retried or goes to recovery.

**Inspecting only the root cause is enough.** False. Error handlers may inspect wrapper exceptions; cause chains and classifiers have specific behaviors. Record both the outer exception and the root cause.

**The retry count in FixedBackOff is always the maximum total attempts for a record.** False when backoff state can reset multiple times due to changing exception classes or recovery failures. Account for reset policies and overall time limits.

**Retry listeners and recoverers are the same callback.** False. Retry listeners observe failures and recoveries; recoverers perform the action on the record after retries end or are skipped.

**Publishing to a DLT means business processing succeeded.** False. A DLT only confirms the record moved to an error-handling stream if publishing succeeded. Business impact still requires investigation and replay or manual handling.

**Non-blocking retry topics follow the same backoff state rules as DefaultErrorHandler.** False. Retry topics use a separate topology and forwarding schedule; evaluate exceptions and ordering under that model.

## 14. Policy selection guide

When designing retries for Spring Kafka listeners, distinguish temporary errors from unrecoverable errors, then decide whether a changing exception class should restart backoff.

A configuration workflow can start as follows:

1. Identify actual exceptions the listener can throw, including wrappers and cause chains.
2. Normalize exceptions at application boundaries to distinguish temporary errors from business errors.
3. Configure classifications for retryable and non-retryable exceptions.
4. Pick a **BackOff** with suitable retry counts, intervals, and caps.
5. Decide **resetStateOnExceptionChange** based on the meaning of a new exception.
6. If reset is enabled, add an overall time limit and monitor alternating exceptions.
7. Configure a clear recoverer and DLT routing.
8. Track delivery attempts, exception classes, root causes, recovery outcomes, and total processing duration.
9. Test changing exceptions, changing wrappers, recovery failures, and restarts.
10. Document the retry policy so operations knows when records redeliver, when they move to DLT, and when intervention is needed.

Exceptions changing between retries are a normal aspect of distributed systems. **resetStateOnExceptionChange** only governs restarting backoff when the exception type changes; it does not replace error classification, time limits, recovery, or idempotency. A reliable policy must control the current error type, retry progression, and the final action on the record.
