# DefaultJmsListenerContainerFactory and Default Configuration in Spring JMS

## 1. What Does the Factory Do?

Spring JMS supports asynchronous message receiving through a listener container. Instead of the application repeatedly calling receive itself, a container manages the JMS connection, session, consumer, the message-receiving loop, and the invocation of the listener when a message arrives.

DefaultJmsListenerContainerFactory is an implementation of JmsListenerContainerFactory. Its job is to create and configure a DefaultMessageListenerContainer for each JMS listener endpoint. This is the default choice that suits most Spring JMS applications because the container supports controlled polling, concurrency, transactions, self-recovery when the broker temporarily loses its connection, and configuration changes at runtime.

You need to distinguish three components:

| Component | Responsibility |
| --- | --- |
| DefaultJmsListenerContainerFactory | Holds the shared configuration and creates containers for endpoints |
| DefaultMessageListenerContainer | Manages the consumer, session, threads, polling, transaction, and the message-receiving lifecycle |
| The @JmsListener method | Processes the payload or message that the container delivers |

The factory does not receive messages directly. When Spring detects a method with @JmsListener, the listener endpoint infrastructure uses the factory to create a dedicated container serving that method.

## 2. Enabling the @JmsListener Infrastructure

In a plain Spring application, place @EnableJms on a configuration class to enable annotation processing:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {
}
~~~

Spring registers the annotation processor and creates listener endpoints from beans that have @JmsListener methods. Each registered method gets a corresponding listener container. The containers' lifecycles are managed through the JmsListenerEndpointRegistry.

If the annotation does not specify a containerFactory, Spring by default looks for a bean named jmsListenerContainerFactory. You can configure the default factory explicitly via JmsListenerConfigurer if you want to use a different name.

Simple listener example:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void receive(String orderId) {
        System.out.println("Received order: " + orderId);
    }
}
~~~

When a message arrives at orders.queue, the container receives the message and calls the receive method. Spring converts the body of the JMS message into the String parameter through the MessageConverter.

## 3. Declaring DefaultJmsListenerContainerFactory

A minimal configuration needs the ConnectionFactory supplied by the JMS provider:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        return factory;
    }
}
~~~

When Spring creates a container for an endpoint, the factory passes the shared configuration into the new DefaultMessageListenerContainer. Afterwards, the endpoint-specific information such as destination, selector, subscription name, and concurrency is applied to the corresponding container.

In Spring Boot, the ConnectionFactory and the default factory can be auto-configured depending on the starter and the broker dependency. In plain Spring Framework, the application must supply the ConnectionFactory bean and configure the broker client, address, authentication, and connection options.

## 4. Important Property Groups

DefaultJmsListenerContainerFactory inherits many properties from AbstractJmsListenerContainerFactory and adds properties specific to DefaultMessageListenerContainer.

### 4.1. Connection and Destination Resolution

| Property | Purpose |
| --- | --- |
| setConnectionFactory | Selects the JMS ConnectionFactory used to connect to the broker |
| setDestinationResolver | Resolves the destination name into a Queue or Topic |
| setPubSubDomain | Selects the default domain: false for queue, true for topic |
| setClientId | Sets the JMS client ID, usually needed for a durable topic subscription |

The ConnectionFactory is a mandatory component for the container to create JMS connections. It is usually provided by ActiveMQ Artemis, IBM MQ, the Amazon SQS JMS wrapper, or another JMS provider.

The DestinationResolver lets the application resolve destination names according to its own rules, for example using JNDI or creating destinations dynamically. If no separate resolver is configured, Spring uses the default mechanism based on the selected queue/topic domain.

### 4.2. Message Conversion

setMessageConverter configures the MessageConverter used to convert a JMS Message into the listener method's arguments and to convert the return value into a JMS reply when reply support is available.

The default SimpleMessageConverter suits basic types such as String, byte array, Map, and Serializable. When exchanging JSON DTOs, you can configure a suitable JSON converter to avoid having to read the TextMessage and parse the body yourself in each listener.

Example of configuring a custom converter:

~~~java
factory.setMessageConverter(orderMessageConverter);
~~~

The orderMessageConverter variable must be a pre-configured MessageConverter bean, for example a Jackson-based converter. The serialization format must be consistent between the producer and the consumer.

### 4.3. Concurrency and Executor

| Property | Meaning |
| --- | --- |
| setConcurrency | Configures the minimum and maximum consumer limits as a string |
| setTaskExecutor | Selects the executor that runs the listener invokers |
| setMaxMessagesPerTask | Limits the number of message receives in one task before the task is rescheduled |

With DefaultMessageListenerContainer, the concurrency value can be a number or a min-max range:

~~~java
factory.setConcurrency("3-10");
~~~

The string 3-10 means the container keeps at least three consumers and can gradually grow to ten as load increases. If you pass "5", the minimum is one and the maximum is five.

Higher concurrency helps the queue process multiple messages concurrently, but the processing order among messages may change. With a topic, be careful when increasing the number of consumers: in a regular configuration, multiple consumers on the same node may receive the same copy of a topic message. Only increase concurrency for a topic when the provider and subscription type clearly support it.

If no TaskExecutor is configured, DefaultMessageListenerContainer uses SimpleAsyncTaskExecutor. This executor creates threads on demand and is not a traditional reusable thread pool. For heavy load or tight resource limits, consider providing a bounded executor and monitoring the number of active threads.

### 4.4. JMS Resource Caching

setCacheLevel or setCacheLevelName determines at what level the container caches the Connection, Session, and MessageConsumer.

Commonly used levels:

| Cache level | Resources held |
| --- | --- |
| CACHE_NONE | Does not cache JMS resources |
| CACHE_CONNECTION | Caches the Connection |
| CACHE_SESSION | Caches the Connection and Session |
| CACHE_CONSUMER | Caches the Connection, Session, and MessageConsumer |
| CACHE_AUTO | Lets the container choose a suitable level according to the transaction strategy |

With local JMS resources, DefaultMessageListenerContainer by default caches the Connection, Session, and Consumer at the CACHE_CONSUMER level. When using an external transaction manager, the default is CACHE_NONE so fresh resources are obtained within the scope of the transaction, which fits the requirements of some Jakarta EE/XA servers.

You should not wrap the listener container with a CachingConnectionFactory by default without reading the container's guidance. DefaultMessageListenerContainer already has its own caching mechanism following its lifecycle; external caching can cause problems when stopping/starting or when the container scales consumers dynamically.

## 5. The Container's Actual Defaults

The factory creates a new DefaultMessageListenerContainer. If not overridden, the container uses these important defaults:

| Container setting | Default | Meaning |
| --- | --- | --- |
| concurrentConsumers | 1 | One consumer minimum |
| maxConcurrentConsumers | 1 | Does not auto-scale to multiple consumers |
| receiveTimeout | 1000 ms | Each polling waits at most one second |
| recoveryInterval | 5000 ms | Tries to recover after about five seconds |
| cacheLevel | CACHE_CONSUMER with local resources; CACHE_NONE with an external transaction manager | Caching according to how transactions are managed |
| sessionTransacted | false | The JMS Session is not transacted |
| sessionAcknowledgeMode | AUTO_ACKNOWLEDGE | The default acknowledge mode |
| maxMessagesPerTask | Usually -1 with a regular TaskExecutor | The invoker task can keep receiving until the container stops |

The container's defaults are the initial foundation. The factory can change these values for all endpoints using it; the annotation or endpoint can override some individual settings, for example concurrency.

### 5.1. receiveTimeout and Polling

DefaultMessageListenerContainer uses a loop that calls MessageConsumer.receive(timeout). receiveTimeout is the wait time of each polling, not the maximum business processing time.

The default 1000 ms lets the container periodically check state, manage tasks, and react to shutdown. Do not set 0 arbitrarily because 0 means wait indefinitely and can make stopping the container harder.

### 5.2. recoveryInterval and BackOff

If the broker is temporarily unavailable or creating the consumer fails, the container tries to recover on its own. By default the interval between attempts is 5000 ms.

You can use setRecoveryInterval to replace the fixed interval, or setBackOff to configure an increasing strategy, for example exponential backoff:

~~~java
factory.setRecoveryInterval(10_000L);
~~~

If you need a more flexible strategy, pass a BackOff implementation:

~~~java
factory.setBackOff(new ExponentialBackOff(1_000L, 2.0));
~~~

Do not configure recoveryInterval and BackOff as two independent policies at the same time without checking the order of application. Setting recoveryInterval creates a fixed backoff and can override a configured BackOff.

## 6. Acknowledge and Transactions: Defaults That Need Careful Evaluation

An important point when configuring the factory is how the container confirms that a message has been processed.

By default sessionTransacted is false and sessionAcknowledgeMode is AUTO_ACKNOWLEDGE. With DefaultMessageListenerContainer, AUTO_ACKNOWLEDGE performs the acknowledge before calling the listener. If the listener throws an exception, the message is not automatically redelivered under this mechanism.

This means a listener can fail after the message has been acknowledged. If the business requires reliable processing, configure an appropriate transaction.

### 6.1. Using a JMS Local Transaction

The common approach in a standalone or ordinary Spring application is to enable sessionTransacted:

~~~java
factory.setSessionTransacted(true);
~~~

In that case, receiving the message and processing in the listener take place within the JMS transaction. If the listener completes normally, the container commits the transaction. If the listener throws an exception, the transaction rolls back and the broker may redeliver the message according to the provider's redelivery policy.

This local transaction covers the JMS operations in the Session. If the listener also updates a database via JDBC, the two resources do not automatically become a single distributed transaction. Design idempotency or an outbox/inbox mechanism to handle the case where the database commits but the JMS commit fails.

### 6.2. Using an External Transaction Manager

If you need to combine JMS with other resources in an XA transaction, you can configure a PlatformTransactionManager, usually a JtaTransactionManager together with an XA-aware ConnectionFactory:

~~~java
factory.setTransactionManager(transactionManager);
~~~

This approach can coordinate message receiving and business processing in a distributed transaction. It requires a broker/provider that supports XA, a correctly configured transaction manager, and has a higher operational cost.

Do not use XA merely to avoid every duplicate. For many applications, a local JMS transaction combined with idempotent processing is the simpler and more effective choice.

### 6.3. Idempotency and Redelivery

Even when using a transaction, duplicates can still occur in some edge cases, for example the JVM stops after the business logic has run but before the JMS transaction commit completes.

The consumer should have an event ID or business key to recognize that a message has already been processed. Recording the processing state needs to be coordinated with the business update so that a redelivered message does not produce unintended repeated effects.

## 7. Configuring One Factory for Multiple Listeners

The following example configures a shared factory for queue listeners:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("2-6");
        factory.setSessionTransacted(true);
        factory.setReceiveTimeout(1_000L);
        factory.setRecoveryInterval(5_000L);

        return factory;
    }
}
~~~

The factory is named jmsListenerContainerFactory, so @JmsListener annotations that do not specify a containerFactory will use it.

Listener:

~~~java
@Component
public class OrderListener {

    @JmsListener(destination = "orders.queue")
    public void handle(String orderId) {
        process(orderId);
    }

    private void process(String orderId) {
        System.out.println("Processing order: " + orderId);
    }
}
~~~

This configuration snippet requires the ConnectionFactory to be provided by the JMS provider and the broker to be running. The example only describes how to configure Spring; the actual stdout depends on the messages sent and when the listener receives them.

## 8. Creating Multiple Factories for Groups of Listeners

Not every listener needs the same concurrency, transaction, or domain. You can create multiple factories with different names:

~~~java
@Configuration
@EnableJms
public class JmsConfiguration {

    @Bean
    public DefaultJmsListenerContainerFactory fastQueueFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("3-8");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean
    public DefaultJmsListenerContainerFactory auditQueueFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

Choosing the factory right on the listener:

~~~java
@Component
public class AuditListener {

    @JmsListener(
        destination = "audit.queue",
        containerFactory = "auditQueueFactory"
    )
    public void handle(String event) {
        writeAudit(event);
    }

    private void writeAudit(String event) {
        System.out.println("Audit: " + event);
    }
}
~~~

The fastQueueFactory factory can serve a high-traffic queue, while auditQueueFactory keeps concurrency low to control ordering and load. Choosing concurrency must be based on processing capacity, the provider's connection/session limits, and the business ordering requirements.

## 9. Per-@JmsListener Attributes

An endpoint can override some of the shared settings from the factory:

~~~java
@JmsListener(
    id = "priorityOrders",
    destination = "orders.queue",
    selector = "priority >= 8",
    concurrency = "2-4"
)
public void handlePriorityOrder(String orderId) {
    processPriorityOrder(orderId);
}
~~~

Commonly used attributes:

| Attribute | Meaning |
| --- | --- |
| destination | The name of the queue or topic to listen on |
| containerFactory | The name of the factory bean used to create the container |
| id | A unique ID for managing the container through the registry |
| selector | The JMS message selector |
| concurrency | Limits consumers for the endpoint; can override the factory's concurrency |
| subscription | The durable subscription name when using an appropriate topic |

If multiple endpoints use the same factory, they can have their own concurrency. There is no need to create a new factory just to change the concurrency for one listener if the annotation already supports that attribute.

## 10. Queue and Topic: Domain Configuration

DefaultJmsListenerContainerFactory inherits setPubSubDomain:

- false: uses a queue, which is the default.
- true: uses a topic.

Example factory for a topic:

~~~java
@Bean
public DefaultJmsListenerContainerFactory topicListenerFactory(
        ConnectionFactory connectionFactory) {

    DefaultJmsListenerContainerFactory factory =
        new DefaultJmsListenerContainerFactory();

    factory.setConnectionFactory(connectionFactory);
    factory.setPubSubDomain(true);
    factory.setSubscriptionDurable(true);
    factory.setClientId("inventory-service");
    factory.setSessionTransacted(true);

    return factory;
}
~~~

A listener can use that factory:

~~~java
@JmsListener(
    destination = "inventory.events",
    subscription = "inventory-audit",
    containerFactory = "topicListenerFactory"
)
public void handleInventoryEvent(String event) {
    recordInventoryEvent(event);
}
~~~

A durable subscription needs a client ID and a subscription name that follow the provider's rules. A shared subscription can be configured separately with setSubscriptionShared(true) when the JMS provider supports it. With a topic, do not increase concurrency arbitrarily because it can cause one node to receive multiple copies of the same message.

If you use queues and topics at the same time, create a separate factory for each domain or configure the endpoint explicitly. Do not let the factory's default pubSubDomain cause a listener to connect to the wrong type of destination.

## 11. ErrorHandler, ExceptionListener, and Observability

The factory can configure two different error-handling mechanisms:

- The ErrorHandler receives unhandled exceptions that arise while invoking the listener.
- The ExceptionListener receives JMSExceptions from the provider or the listener infrastructure. If an ErrorHandler is also configured, some JMSExceptions may continue to be passed to the ErrorHandler after the ExceptionListener.

Example:

~~~java
factory.setErrorHandler(error ->
    logger.error("JMS listener failed", error)
);
~~~

If no ErrorHandler is configured, exceptions from the listener are logged at WARN level according to the container's default behavior. Exceptions are not automatically propagated back to the JMS provider as a listener failure.

You can configure an ExceptionListener to observe connection errors or JMS errors at the provider layer:

~~~java
factory.setExceptionListener(exception ->
    logger.error("JMS provider error", exception)
);
~~~

Spring Framework 6.1+ also supports ObservationRegistry for recording observations of message processing. When a Micrometer ObservationRegistry is available, it can be configured through the factory to track processing time and appropriate observation information.

Do not treat the ErrorHandler as a retry or redelivery mechanism. Retry and redelivery need to be decided by the transaction, acknowledgement, broker policy, or a separate retry mechanism.

## 12. Recovery, Shutdown, and Lifecycle Management

DefaultMessageListenerContainer implements SmartLifecycle, so Spring manages starting and stopping along with the application context.

Notable properties:

- setAutoStartup(false): does not automatically start the container when the context starts.
- setPhase(...): controls the relative start/stop order among lifecycle components.
- setRecoveryInterval(...): configures the interval for reconnection attempts.
- setBackOff(...): configures the retry strategy when the container cannot establish the listener.
- setTaskExecutor(...): manages the threads that run the listener.

When the broker loses its connection, the container can recover on its own and recreate the JMS resources. Observe the recovery logs, the number of active consumers, the number of reconnects, and the queue state.

On shutdown, the container stops the consumers and releases the session/connection following its lifecycle. If a listener is processing a message for a long time, determine an appropriate shutdown time and avoid stopping the broker or the JVM too abruptly.

## 13. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| @JmsListener is not registered | @EnableJms is missing or the listener bean is not managed by Spring | Enable annotation support and check component scanning |
| The container factory is not found | The bean name is not jmsListenerContainerFactory and the annotation does not specify a factory | Set the correct default name or use an explicit containerFactory |
| The listener connects to the wrong queue/topic | pubSubDomain is not the right domain | Use a separate factory or set an appropriate pubSubDomain |
| The listener processes sequentially although parallelism is desired | concurrentConsumers is still 1 | Increase concurrency after checking ordering and broker capacity |
| A message is lost when the listener throws an exception | The default AUTO_ACKNOWLEDGE of DefaultMessageListenerContainer acknowledges before the listener | Enable sessionTransacted or use a transaction manager |
| A message is processed repeatedly | Broker redelivery or the transaction commit did not complete | Design an idempotent consumer using an event ID/business key |
| The broker recovers slowly | recoveryInterval is too long or the BackOff is unsuitable | Adjust recovery/backoff according to the SLA and reconnect limits |
| Threads grow uncontrollably | The default SimpleAsyncTaskExecutor creates threads on demand | Provide a bounded TaskExecutor and monitor the load |
| A topic receives duplicate messages within the same application | Concurrency on the topic was increased incorrectly | Keep a single consumer or use a shared subscription depending on provider capability |
| The cache causes stop/start errors | The listener container is wrapped with an unsuitable CachingConnectionFactory | Prefer the cache managed by the container and check the transaction strategy |

## 14. Production Configuration Checklist

- [ ] Provide a ConnectionFactory with the correct broker, endpoint, and credentials.
- [ ] Enable @EnableJms in a plain Spring application.
- [ ] Name the default factory jmsListenerContainerFactory or specify containerFactory explicitly on each endpoint.
- [ ] Determine whether it is a queue or a topic and configure the corresponding pubSubDomain.
- [ ] Choose concurrency according to load, message ordering, and broker resource limits.
- [ ] Configure sessionTransacted or a transaction manager when reliable redelivery is needed.
- [ ] Design idempotent listeners to handle duplicates.
- [ ] Check the message converter and the payload schema.
- [ ] Configure the ErrorHandler, ExceptionListener, recovery/backoff, and logging.
- [ ] Configure a bounded executor if using a separate thread pool.
- [ ] Check that the cache level suits the transaction manager and the provider.
- [ ] Test broker restart, listener exception, redelivery, queue backlog, and shutdown.
- [ ] Monitor active consumers, processing latency, redelivery count, error rate, and recovery attempts.

## 15. References

- [Spring Framework — Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework API — DefaultJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html)
- [Spring Framework API — AbstractJmsListenerContainerFactory](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/config/AbstractJmsListenerContainerFactory.html)
- [Spring Framework API — JmsListener](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/annotation/JmsListener.html)
- [Spring Framework API — DefaultMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework API — AbstractMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html)
- [Spring Framework API — AbstractPollingMessageListenerContainer](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
