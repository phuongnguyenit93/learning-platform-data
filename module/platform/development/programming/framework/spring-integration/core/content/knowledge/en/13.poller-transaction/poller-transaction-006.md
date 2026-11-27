# Retry around a poller

## 1. Goals and context

In the **SPRING_INTEGRATION_CORE** module, a message flow is assembled from Message, MessageChannel, endpoints, gateways, and Java DSL. This lesson belongs to the **Poller transaction** chapter and focuses on retrying a polling operation upon transient errors while maintaining accurate transaction boundaries and message-processing semantics.

After this lesson, you will be able to:

- Distinguish polling schedule, retry within a single poll, and redelivery from the source.
- Choose between retrying around the poller or retrying at a single handler.
- Order retry advice and transaction advice according to your goal.
- Explain why rollback does not automatically return every message to its source.
- Design retry limits, backoff, error paths, and behavioral verification.

**Example scope:** Java code uses Spring Integration **6.5.x**, Spring Retry **2.0.x**, and Java 17 or higher. The example requires Spring Integration Core and Spring Retry; the JDBC example additionally requires Spring Integration JDBC, Spring JDBC, and the appropriate driver. Dependency versions should be managed by your project's BOM. Do not mix the Spring Retry imports in this lesson verbatim with Spring Integration 7.x's retry API: the 7.x branch moved retry mechanics into Spring Framework. See [retry documentation for branch 6.5](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/classes.html) and [RequestHandlerRetryAdvice API in branch 7.x](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/advice/RequestHandlerRetryAdvice.html).

## 2. What is the poller wrapping?

Two scenarios are common:

| Component | Polled source | Action after receiving |
|---|---|---|
| SourcePollingChannelAdapter | MessageSource, such as a JDBC source or custom source | Sends Message into output channel |
| PollingConsumer | PollableChannel, such as QueueChannel | Invokes the endpoint's MessageHandler |

One receive-and-process cycle can be pictured as:

~~~text
receive()
   |
   +-- null ----------------------> no data, end receive
   |
   +-- Message --> process/forward --> succeed or throw exception
~~~

Standard poller advice wraps this receive and synchronous processing. When advice retries, it may re-invoke `receive()` as well. This differs from holding onto the same Message and only re-invoking a single service. Endpoint types are described in [Poller](https://docs.spring.io/spring-integration/reference/6.5/polling-consumer.html).

Consider an order flow:

~~~text
Order source
   -> poller
   -> normalizing transformer
   -> validating filter
   -> partner-selecting router
   -> partner-calling gateway
   -> write result
~~~

If the gateway fails and the exception unwinds to the poller on the same call stack, retrying around the poller may re-execute steps preceding the gateway. This must be evaluated against each step's side effects, such as writing audit logs, reserving inventory, or creating payment requests. [Adding Behavior to Endpoints](https://docs.spring.io/spring-integration/reference/6.5/handler-advice.html) explains why attaching separate advice on endpoints is necessary.

### 2.1. One scheduler tick can contain multiple receives

`maxMessagesPerPoll` limits how many message-bearing receives occur in one scheduled tick. It is not a retry count. With a standard synchronous poller in branch 6.5, the standard advice chain is attached to the polling task that performs a single receive and process; the scheduler tick loop invokes that task multiple times.

Therefore, `maxMessagesPerPoll(10)` does not automatically combine ten messages into one shared transaction. This lesson uses `maxMessagesPerPoll(1)` to observe each receive-and-process unit clearly. You can verify this in [AbstractPollingEndpoint 6.5.0 source code](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/endpoint/AbstractPollingEndpoint.java).

## 3. Three commonly confused mechanisms

| Mechanism | Who triggers the next attempt? | Where does the counter belong? | Guarantees the same Message? |
|---|---|---|---|
| Polling schedule | Scheduler and Trigger | Scheduled tick | No |
| Retry around poller | Retry advice | A single execution managed by advice | Not guaranteed; may re-receive |
| Redelivery | Broker, transactional store, or source logic | Source redelivery policy | Depends on source mechanism and business identifier |

Consider a poller configured to run every second and retry up to three attempts:

~~~text
Tick 1:
  attempt 1 -> transient error
  wait 100 ms
  attempt 2 -> transient error
  wait 200 ms
  attempt 3 -> succeeds

Tick 2:
  a new poll, with a fresh retry budget
~~~

In Spring Retry 2.0.x, `maxAttempts = 3` includes the initial attempt, meaning at most two retries. There is no sleep after the final attempt. The attempt-counting contract is stated in [SimpleRetryPolicy](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/policy/SimpleRetryPolicy.html).

If all three attempts fail, the scheduler can still execute the next tick. With a rollback-capable source, the same event may reappear on that tick and receive a fresh budget of three attempts. Thus, one retry invocation's limit is not the total processing limit for an event.

When `receive()` returns `null`, the source is reporting no message is available. This is not an exception for a standard policy to retry. Do not throw fake exceptions merely to force the poller to keep probing an empty source.

## 4. Choosing retry scope

### 4.1. Retry around the poller

Suitable when errors happen while accessing the source or when the entire transactional unit—receive and processing—must be retried.

Examples:

- The source-reading connection drops briefly before data is fetched.
- A deadlock forces the receive-and-order-update transaction to roll back.
- The source supports redelivery and synchronous steps can be safely re-executed.

The advice used in the example is `RetryOperationsInterceptor`, a general `MethodInterceptor` from Spring Retry. It is passed into `Pollers...advice(...)`, not attached to a handler.

### 4.2. Retry at the handler

If you only want to re-invoke a service with an already-received Message, consider `RequestHandlerRetryAdvice` on that endpoint. On branch 6.5, you can configure the same kind of RetryTemplate, but you need an advice designed for request handlers:

~~~java
import org.springframework.integration.handler.advice.RequestHandlerRetryAdvice;
import org.springframework.retry.support.RetryTemplate;

// Inside a @Bean method:
RequestHandlerRetryAdvice advice = new RequestHandlerRetryAdvice();
advice.setRetryTemplate(handlerRetryTemplate);
return advice;
~~~

`handlerRetryTemplate` is a RetryTemplate dedicated to the service operation's policy. In Java DSL, this advice is configured on the handling endpoint:

~~~java
.handle(partnerService, "submit", endpoint -> endpoint.advice(partnerRetry))
~~~

Here `partnerService` is the service bean and `partnerRetry` is the RequestHandlerRetryAdvice. Placing `RequestHandlerRetryAdvice` on the poller is not an equivalent substitute for a general MethodInterceptor; that advice is built for message-handling calls.

### 4.3. Retrying only the read operation

If you need to retry reading the source while wanting downstream processing to run only once, wrap the MessageSource read call with a RetryTemplate and let downstream errors follow their own mechanism.

Spring Integration also provides `ReceiveMessageAdvice` for receive operations. However, this interface does not add a retry policy on its own; choosing or writing an implementation must still obey its contract. When combining multiple advice types, verify actual scopes rather than looking only at bean name order.

| Need | Preferred attachment point |
|---|---|
| Recover from brief source-access failures | Around poller or read operation specifically |
| Retry an HTTP call with the same payload | Advice on the handler/gateway making the HTTP call |
| Roll back and re-receive a unit of work | Poller retry outside transaction, paired with a transactional source |
| Wait minutes or hours | Scheduled redelivery mechanism, retry queue, or durable scheduler |

## 5. Java DSL example: source fails twice then succeeds

The following example is a complete Spring configuration for **errors before the source emits a Message**. It deliberately restricts retryable exceptions, configures backoff, and provides dedicated channels for results and errors.

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageSource;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.interceptor.RetryInterceptorBuilder;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Configuration
@EnableIntegration
public class PollerRetryDemo {

    @Bean
    AtomicInteger sourceReadCounter() {
        return new AtomicInteger();
    }

    @Bean
    RetryOperationsInterceptor pollRetry() {
        Map<Class<? extends Throwable>, Boolean> retryable =
                Map.of(TransientDataAccessException.class, true);

        SimpleRetryPolicy policy =
                new SimpleRetryPolicy(3, retryable, true, false);

        ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
        backoff.setInitialInterval(100);
        backoff.setMultiplier(2.0);
        backoff.setMaxInterval(1_000);

        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(policy);
        template.setBackOffPolicy(backoff);

        return RetryInterceptorBuilder.stateless()
                .retryOperations(template)
                .build();
    }

    @Bean
    MessageSource<String> demoSource(AtomicInteger sourceReadCounter) {
        AtomicBoolean emitted = new AtomicBoolean();

        return () -> {
            if (emitted.get()) {
                return null;
            }

            int attempt = sourceReadCounter.incrementAndGet();
            if (attempt <= 2) {
                throw new TransientDataAccessResourceException(
                        "Source not ready, read attempt " + attempt);
            }

            emitted.set(true);
            return MessageBuilder.withPayload("order-1042")
                    .setHeader("eventId", "evt-1042")
                    .build();
        };
    }

    @Bean
    QueueChannel demoResults() {
        return new QueueChannel(10);
    }

    @Bean
    QueueChannel pollErrors() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow demoFlow(
            MessageSource<String> demoSource,
            RetryOperationsInterceptor pollRetry,
            @Qualifier("demoResults") QueueChannel demoResults,
            @Qualifier("pollErrors") QueueChannel pollErrors) {

        return IntegrationFlow
                .from(demoSource, endpoint -> endpoint
                        .id("demoSourcePoller")
                        .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                                .maxMessagesPerPoll(1)
                                .advice(pollRetry)
                                .errorChannel(pollErrors)))
                .transform(String.class, String::toUpperCase)
                .channel(demoResults)
                .get();
    }
}
~~~

Key decisions to read from the configuration:

- The policy allows up to three attempts and retries only TransientDataAccessException and its subclasses.
- `traverseCauses = true` searches wrapped exceptions for a matching cause; `defaultValue = false` excludes errors not listed in the policy.
- Backoff is 100 ms and 200 ms respectively when the first two attempts fail.
- No recoverer is declared, so the final error continues propagating out of the advice.
- `pollErrors` and `demoResults` are small-capacity in-memory QueueChannels for illustrative observation.
- AtomicBoolean only remembers whether the demo source has emitted data; it provides neither rollback nor durability.

Creating the interceptor via `RetryInterceptorBuilder.stateless().retryOperations(template)` is supported in [RetryInterceptorBuilder 2.0.x](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/interceptor/RetryInterceptorBuilder.html). When custom RetryOperations are supplied, policy and backoff are configured on that template.

The expected result is payload `ORDER-1042` on `demoResults` and a read counter of 3. Subsequent polling ticks return null.

**Important limitation:** the demo source marks itself as emitted before downstream finishes. If the transformer or downstream send fails afterward, a new attempt will see null. This example demonstrates retrying source-read errors, not redelivering a Message after processing fails.

## 6. Retry and transaction: order determines behavior

Advices are layers wrapping an invocation. In a standard advice chain, the first element is outermost. These two structures mean different things:

~~~text
A. Retry(Tx(receive + process))

attempt 1: begin T1 -> error -> rollback T1
backoff
attempt 2: begin T2 -> error -> rollback T2
backoff
attempt 3: begin T3 -> succeeds -> commit T3

B. Tx(Retry(receive + process))

begin T
  attempt 1 -> error
  backoff
  attempt 2 -> error
  backoff
  attempt 3 -> succeeds or error
commit/rollback T
~~~

This wrapping rule is presented in [Ordering Advices within Advice Chain](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/order.html).

### 6.1. Retry outside transaction

When an attempt must roll back completely before the next attempt, structure A is usually chosen:

~~~java
.advice(pollRetry, pollTransaction)
~~~

With REQUIRED propagation and no outer transaction on the poller thread, each attempt creates a fresh transaction. When an error matching rollback rules passes through the transaction advice, the transaction ends before retry advice waits for backoff.

Verify all three conditions together:

1. The exception actually escapes the transactional block.
2. The transaction manager manages the resources that need rollback.
3. The source can redeliver the work after rollback.

Placing retry advice outside does not by itself guarantee a fresh physical transaction if an outermost transaction already exists and REQUIRED simply joins it.

### 6.2. Transaction outside retry

With structure B, waiting for backoff happens inside the outer transaction scope. Connections, locks, or persistence state may be held longer.

If a participating component has marked rollback-only, a later successful attempt does not clear that flag. At commit time, UnexpectedRollbackException may occur. Not every exception sets rollback-only automatically; behavior depends on the transaction advice, resource, and rollback rules. These points are explained in [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

Additionally, if retry catches the error and a recoverer returns normally, the outer transaction may see a successful invocation if rollback-only was not set. Thus, never use "sent an error to a channel" as proof that a transaction rolled back.

### 6.3. Do not use REQUIRES_NEW as an automatic fix

REQUIRES_NEW can separate transactions, but it also changes flow atomicity. A child step committing on its own while the message-receive step rolls back can cause the child step to run again on redelivery.

Before using it, identify which outcomes must commit together, whether an outer transaction exists, and whether the connection pool has sufficient capacity. In an example where the poller initiates the transaction with no outer transaction, REQUIRED already satisfies the one-transaction-per-attempt goal.

## 7. Transactional example: receiving from a JDBC-backed QueueChannel

This example chooses PostgreSQL to clearly demonstrate a transactional source. The goal is to bind taking a message from the channel and writing the result into the same local transaction.

Preconditions:

- A DataSource for PostgreSQL.
- Spring Integration JDBC, Spring JDBC, Spring TX, and the PostgreSQL driver.
- Message store schema initialized from the matching script in Spring Integration JDBC.
- A business table `order_result`; `event_id` has a unique constraint or primary key.
- Queue store, JdbcTemplate, and transaction manager share **the same DataSource bean**.
- Processing runs synchronously, without intermediate ExecutorChannel or QueueChannel hops.

Example business table:

~~~sql
CREATE TABLE order_result (
    event_id VARCHAR(100) PRIMARY KEY,
    order_code VARCHAR(100) NOT NULL
);
~~~

Place the bean methods below in a configuration class annotated with `@Configuration` and `@EnableIntegration`. Reuse the `pollRetry` bean from the previous section; there is no need to enable `demoFlow`, `demoSource`, or the demo's observation beans in the JDBC application.

~~~java
import java.time.Duration;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.MessageChannels;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.transaction.TransactionInterceptorBuilder;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.messaging.MessageHandler;
import org.springframework.retry.interceptor.RetryOperationsInterceptor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.interceptor.TransactionInterceptor;

// Methods inside the configuration class:

@Bean
JdbcChannelMessageStore ordersStore(DataSource dataSource) {
    JdbcChannelMessageStore store = new JdbcChannelMessageStore(dataSource);
    store.setChannelMessageStoreQueryProvider(
            new PostgresChannelMessageStoreQueryProvider());
    return store;
}

@Bean
QueueChannel orders(JdbcChannelMessageStore ordersStore) {
    return MessageChannels.queue(ordersStore, "orders")
            .getObject();
}

@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}

@Bean
TransactionInterceptor pollTransaction(
        PlatformTransactionManager transactionManager) {

    return new TransactionInterceptorBuilder()
            .transactionManager(transactionManager)
            .propagation(Propagation.REQUIRED)
            .timeout(5)
            .build();
}

@Bean
MessageHandler orderHandler(DataSource dataSource) {
    JdbcTemplate jdbc = new JdbcTemplate(dataSource);

    return message -> {
        String eventId = message.getHeaders().get("eventId", String.class);
        if (eventId == null) {
            throw new IllegalArgumentException("Missing eventId");
        }

        jdbc.update("""
                INSERT INTO order_result(event_id, order_code)
                VALUES (?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                eventId,
                message.getPayload().toString());
    };
}

@Bean
IntegrationFlow ordersFlow(
        @Qualifier("orders") QueueChannel orders,
        RetryOperationsInterceptor pollRetry,
        TransactionInterceptor pollTransaction,
        @Qualifier("orderHandler") MessageHandler orderHandler) {

    return IntegrationFlow.from(orders)
            .handle(orderHandler, endpoint -> endpoint
                    .id("ordersPollingConsumer")
                    .poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                            .receiveTimeout(0)
                            .maxMessagesPerPoll(1)
                            .advice(pollRetry, pollTransaction)))
            .get();
}
~~~

Notes when reading the example:

- `timeout(5)` on the transaction builder is in **seconds**.
- `receiveTimeout(0)` is the wait duration for receiving from the channel, in **milliseconds**; 0 means do not wait.
- No recovery callback is declared on the retry advice.
- PostgreSQL ON CONFLICT ensures the single-row insert does not add duplicate rows when the same eventId arrives again. This is a simple rule for the example, assuming the same eventId always represents the same business content.
- `ON CONFLICT` does not catch payload differences between two distinct events accidentally reusing an eventId; production systems must decide whether to detect or reject that case.

The API for creating a channel with a message store is in [MessageChannels 6.5.0](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/MessageChannels.html). Advice configuration APIs are in [TransactionInterceptorBuilder](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/transaction/TransactionInterceptorBuilder.html) and [PollerSpec](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/PollerSpec.html).

### 7.1. What happens when writing the result hits a deadlock?

Suppose PostgreSQL reports an error translated into TransientDataAccessException:

~~~text
retry advice
  -> begin transaction T1
  -> receive from JDBC channel
  -> INSERT order_result hits deadlock
  -> exception propagates out
  -> rollback T1: message removal and DB changes are undone
  -> backoff outside T1
  -> begin transaction T2
  -> receive an available work item again
  -> process successfully
  -> commit T2
~~~

Rollback allows the partially processed work to return to an available state. In a multi-consumer environment, do not assert that the next attempt always picks up the exact same Message or exact same order: another consumer may pick it up first, or selection rules may change the order.

Schema requirements, query providers, and store characteristics are described in [JDBC Message Store](https://docs.spring.io/spring-integration/reference/6.5/jdbc/message-store.html).

### 7.2. Messages sent into the example

A producer can send a Message containing a String payload and eventId:

~~~java
orders.send(MessageBuilder.withPayload("ORDER-1042")
        .setHeader("eventId", "evt-1042")
        .build());
~~~

In the example, payload and headers are kept simple to suit persistence. When using the JDBC store's default serializer, payloads and custom headers must be compatible with the serialization mechanism. Do not put arbitrary runtime objects such as connections or service beans into headers for persistent storage.

### 7.3. Why is an in-memory QueueChannel not equivalent?

With `new QueueChannel()`:

~~~text
receive A -> A is removed from queue
handler error
DB transaction rollback
retry receive -> may receive B or null
~~~

A DB transaction does not automatically return A to an in-memory queue. The consequence can be subtle: the handler fails on A, the next attempt receives null, and the retry invocation finishes normally even though A was never processed.

Likewise, a database rollback does not automatically undo a moved file, a sent HTTP request, or a dispatched email. Post-transaction synchronization callbacks also do not turn a non-transactional resource into a rollback-capable one. The role of bringing receive into the transaction is explained in [Poller Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

## 8. Thread boundaries and error visibility

Retry advice can catch only exceptions that pass through the invocation scope it wraps.

~~~mermaid
flowchart LR
    S["Transactional source"] --> P["Poller: Retry outside Tx"]
    P --> D["DirectChannel"]
    D --> H["Synchronous handler"]
    H --> DB["Database in same transaction"]
    P --> E["ExecutorChannel or intermediate QueueChannel"]
    E --> W["Consumer on another thread"]
~~~

The two branches in the diagram illustrate two different ways forward. In the synchronous branch, exceptions can propagate back to the poller. In the branch handing off to another thread, the poller typically observes only the hand-off.

Example:

~~~text
poller -> DirectChannel -> partner call fails
          exception returns to poller if not handled in between

poller -> ExecutorChannel -> hand-off succeeds
                              |
                              +-> another thread calls partner and fails
~~~

In the second example, retry around the poller will not re-run on a late error occurring on another thread. A retry or redelivery policy is needed on the side actually performing the work, along with an appropriate error-reporting mechanism.

If the flow has a gateway configured to turn errors into responses, a filter dropping Messages, or a component catching exceptions and returning normally, the poller can also see success. With an aggregator, receiving one part and persisting state successfully does not mean the entire group has been aggregated and processed successfully; errors occurring when the group completes must be handled at that point.

Exception propagation behavior between DirectChannel and asynchronous channels is described in [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

## 9. When retries are exhausted: rollback, error reporting, and recovery

Decide three distinct things clearly:

1. Should the current transaction commit or roll back?
2. Can the work item be redelivered by the source?
3. Where are errors observed, persisted, and handled?

### 9.1. Letting the exception propagate out

In the Retry(Tx(...)) structure, if there is no recoverer and the final attempt fails:

~~~text
final attempt fails
  -> transaction advice rolls back
  -> retry advice throws final error
  -> polling task error-handling mechanism receives exception
  -> may publish ErrorMessage per error handler/error channel config
~~~

In the JDBC example, no dedicated error channel is configured, so Spring Integration's default error mechanism is used. In the Section 5 demo, polling errors are routed to `pollErrors`.

Configuring an error channel only specifies where error notifications go. It does not automatically schedule reprocessing, create a dead-letter queue, or durably keep a copy of the Message.

### 9.2. Recovery returning normally has business meaning

A recovery callback is typically used to produce a fallback result or route the failure to an alternate handling path. When the callback returns normally, outer layers may treat the invocation as handled.

Recovery placement must be evaluated alongside advice order:

| Structure | Where does recovery normally run? | What to watch out for |
|---|---|---|
| Retry(Tx(...)) | After the final attempt's transaction ends | Writing an error record needs its own storage/transaction scope if durability is required |
| Tx(Retry(...)) | Inside the outer transaction | The callback may contribute to a committed result, or still fail due to rollback-only |

A recoverer on an interceptor around the poller also does not automatically receive the business Message the way a handler recoverer does: the advised call may be a polling task with no Message argument. If the source fails before receive, no Message exists yet. Do not force every polling error into a structure that assumes failedMessage always exists.

### 9.3. Do not create an infinite error loop

A common problematic design:

~~~text
poller exhausts retries
  -> errorChannel
  -> send immediately back to source
  -> poller retries again
  -> errorChannel
  -> ...
~~~

You need an overall policy keyed by eventId: cumulative failure count, next processing time, deadline, and final action. If failure counts must persist across polling ticks or restarts, store that information in the source or an appropriate state store.

In particular, a counter updated inside the very transaction that rolls back will lose its update. When designing a durable counter, specify clearly where it commits and how to handle failures when updating the counter itself.

## 10. Bounded and reasoned retry policies

### 10.1. Classifying errors by likelihood of succeeding next time

| Error | Usually suitable handling | Additional conditions to check |
|---|---|---|
| Deadlock, transient lock contention | Retry entire transactional unit | Rollback finishes before next attempt |
| Brief source connection error | Retry with backoff | Recovery time fits within budget |
| Timeout calling an external service | Conditional retry | Partner may already have completed the operation |
| Invalid payload schema, missing eventId | Route to error/invalid-data path | Retrying will not fix the payload |
| Wrong credentials or invalid SQL config | Report configuration error | Requires config change or manual intervention |
| Message failing deterministically every time | Quarantine per policy | Avoid blocking other Messages indefinitely |

Do not use `Exception.class` for all cases just to keep config short. Even an error classified as transient by a library must be evaluated against time budgets and the operation's side effects.

### 10.2. Backoff is part of the time budget

With at most A attempts, if each attempt has budget T and wait intervals are b1 through b(A-1):

~~~text
Approximate thread occupancy time
    <= A * T + b1 + b2 + ... + b(A-1) + overhead
~~~

This is an estimate only when each attempt is genuinely time-bounded. A transaction timeout does not replace a connect timeout, read timeout, or the timeout of an arbitrary I/O call.

For example, three attempts, each taking up to around 800 ms, with 100 ms and 200 ms backoffs:

~~~text
3 * 800 + 100 + 200 = 2,700 ms, excluding overhead
~~~

If the poller uses a one-second fixedDelay, the next tick in synchronous execution starts after the current tick finishes and the delay elapses. Do not expect polling strictly every one second when a single invocation takes nearly three seconds.

Blocking backoff holds the executing thread. If multiple pollers share a small-thread scheduler, one failing source can slow down other flows. For long waits, consider scheduled redelivery rather than sleeping a thread for a long time. Jitter can help prevent instances from retrying in lockstep, though the ExponentialBackOffPolicy example in this lesson does not enable randomization.

### 10.3. Avoid multiplying call counts across layers

Suppose:

~~~text
HTTP client: max 3 attempts
handler retry: max 3 attempts
poller retry: max 3 attempts
~~~

In the worst case, a single poll can generate up to `3 * 3 * 3 = 27` HTTP calls if all three layers wrap and repeat that same operation. Redelivery on subsequent ticks can multiply it further.

Assign primary responsibility for each error class to one layer, document the total budget, and avoid configuring multiple independent policies without calculating their combined effect.

## 11. Retry, redelivery, and idempotency

Typical scenario:

~~~text
attempt 1:
  POST create shipment -> partner created it
  connection drops before response reaches application
  application sees timeout

attempt 2:
  POST create shipment again
~~~

A database rollback on the application side does not delete the shipment already created at the partner. To control this scenario, use eventId as an idempotency key if the partner API supports it, or reconcile results using a stable request identifier.

For processing contained within the same database, use a unique constraint combined with business writes in the same transaction. The `order_result` example in Section 7 creates only one row per eventId. If business logic has multiple other updates, the processed marker and those updates must share the same atomic boundary.

Identifiers to distinguish:

| Identifier | Meaning |
|---|---|
| MessageHeaders.ID | Identifier of a Message in Spring Messaging |
| eventId or business key | Stable identifier of the business event or operation |
| Retry attempt | Execution count within a single retry invocation |
| Delivery attempt | Number of times the source has delivered the work per source policy |

When the source creates a new Message for the same event, MessageHeaders.ID can change. Do not rely on it by default for business deduplication across redeliveries.

Stateful retry allows linking retry state across redeliveries using a stable key, but it does not make a broker or source redeliver on its own. Also verify whether retry state persists across restarts. In this lesson, the interceptor is created as stateless; it does not maintain limits across polling ticks.

## 12. Verifying examples and transactional behavior

The test snippets below are practice guidelines; this lesson does not assume they have already been run in your project environment.

### 12.1. Testing a transiently failing source before emitting a Message

Using the PollerRetryDemo class from Section 5 and JUnit Jupiter:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class PollerRetryDemoTest {

    @Test
    void retriesSourceFailuresBeforePublishing() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(PollerRetryDemo.class)) {

            QueueChannel results =
                    context.getBean("demoResults", QueueChannel.class);
            QueueChannel errors =
                    context.getBean("pollErrors", QueueChannel.class);
            AtomicInteger counter =
                    context.getBean("sourceReadCounter", AtomicInteger.class);

            Message<?> result = results.receive(5_000);

            assertNotNull(result);
            assertEquals("ORDER-1042", result.getPayload());
            assertEquals("evt-1042", result.getHeaders().get("eventId"));
            assertEquals(3, counter.get());
            assertNull(errors.receive(0));
        }
    }
}
~~~

The test waits for the result on the channel with a finite timeout. It does not assert exact wall-clock backoff timing. The five-second limit is a test wait timeout, not the retry policy's timeout.

This tests the scope of retrying source reads. It does not yet verify rollback, the JDBC store, or re-invoking the same Message after downstream failures.

### 12.2. Scenarios to test with an appropriate real database

| Scenario | How to inject controlled errors | Evidence to gather |
|---|---|---|
| Transient error then success | Handler throws TransientDataAccessException the first two times | Rollback before next attempt; one final result committed |
| Persistent error | Handler always throws transient error | Three attempts in invocation; work remains receivable after rollback |
| Non-retryable error | Handler throws IllegalArgumentException | One attempt in invocation; goes to error path |
| Distinguish both advice orders | Swap pollRetry and pollTransaction in test config | Transaction start/end and rollback-only match expectations |
| In-memory queue | Receive A then trigger downstream error | A does not automatically return just because DB rolled back |
| Async boundary | Put failing handler after ExecutorChannel | Error does not propagate back to poller that finished hand-off |
| Redeliver same eventId | Send the same event again | No extra order_result row created |
| Error before receive | Source throws exception before building Message | Error path does not assume failedMessage is always present |

To count exactly one retry invocation with a running scheduler, control endpoint lifecycle or pause after receiving the invocation's final error. If the poller keeps running, the next tick can push the counter past three and skew test conclusions.

When measuring transactions, record TransactionSynchronization callbacks or begin/commit/rollback events from a wrapped transaction manager for observation. Checking `isActualTransactionActive()` alone is not enough to prove attempts belong to separate transactions.

Do not put `@Transactional` on the outer test and infer scheduler-thread transactions: the test thread's transaction context does not automatically propagate to the poller thread. For PostgreSQL SQL and locking behavior, test on PostgreSQL rather than inferring entirely from a database with different semantics.

## 13. Observation and diagnostics

A useful observation record may contain:

~~~text
endpoint=ordersPollingConsumer
eventId=evt-1042
retryInvocation=local-cycle-17
attempt=2
maxAttempts=3
exception=TransientDataAccessException
outcome=ROLLBACK
nextBackoffMs=200
~~~

This is a suggested application format, not a default log Spring guarantees to emit. Before receive, eventId may not exist yet; in that case prioritize endpoint, source details, and polling-run correlation ID.

Metrics to track include invocations needing retry, attempt counts, exhausted-retry invocations, processing duration including backoff, age of unfinished work, and redelivery counts per eventId. Do not put unbounded-cardinality eventId values as metric labels; keep them in logs or traces for lookup.

| Symptom | Possibilities to check |
|---|---|
| Configured 3 attempts yet logs show dozens | Multiple polling ticks, multiple retry layers, or redelivery |
| Retry reports success yet data is missing | Subsequent attempt received null from a non-rollback-capable source |
| UnexpectedRollbackException after handler succeeds | Shared transaction was already marked rollback-only |
| No retry seen when handler fails | Error on another thread, converted to response, or caught mid-flow |
| Other pollers slow down | Backoff or I/O occupying the scheduler thread |
| Same partner action executed multiple times | Broad retry scope and missing idempotency |
| ErrorMessage arrives yet work does not rerun | Error channel not wired to a redelivery policy |

## 14. Decision workflow

Before adding retry around a poller, answer in order:

1. **Which operation may repeat?** Only reading the source, one handler, or the full receive-and-process unit?
2. **How can the source redeliver?** Transactional receive rollback, broker mechanics, or application logic?
3. **Which resources share the transaction?** Identify the transaction manager and participating DataSources or resources.
4. **Does the exception reach the advice?** Check thread boundaries and components that turn errors into normal results.
5. **What state does the next attempt start in?** Has the prior transaction ended or is it still rollback-only?
6. **How long and how many times to retry?** Account for client, handler, poller retries, and redeliveries combined.
7. **What to do when it cannot succeed?** Persist failure, quarantine, reconcile, or require intervention per policy.
8. **Can side effects tolerate re-execution?** Apply business identifiers and idempotency in the right place.
9. **What is the verification evidence?** Observe attempts, transactions, committed data, and source state.

Retry around a poller fits when the repetition scope matches a re-executable unit of work. To apply it correctly, determine together what call the advice wraps, the source's rollback capability, and the side effects of endpoints in the flow.
