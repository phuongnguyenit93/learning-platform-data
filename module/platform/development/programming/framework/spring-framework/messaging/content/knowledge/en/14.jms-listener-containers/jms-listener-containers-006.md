# TaskExecutor, receiveTimeout, and Consumer Idle Time in Spring JMS

## 1. Three factors working together in the listener container

DefaultMessageListenerContainer (DMLC) receives messages with a loop that calls MessageConsumer.receive(timeout). Each consumer has one JMS Session, one MessageConsumer, and one listener task running asynchronously. Three configuration settings determine how the container uses threads and keeps consumers when the destination has no messages:

- **TaskExecutor** determines which thread the listener task runs on and how it is scheduled.
- **receiveTimeout** determines how long each receive call waits for a message at most.
- **The idle limits** determine when a surplus consumer is kept or stopped after several attempts that received no message.

These properties are closely tied to concurrency. They affect how quickly consumers increase when the queue has load, how quickly consumers are released when the queue is quiet, and the number of threads/JMS resources held throughout the container's lifecycle.

You need to distinguish consumer idle time from message processing time. receiveTimeout only applies while the consumer is waiting for a message. If the listener has already received a message and is processing a job that takes 30 seconds, a receiveTimeout of 1 second does not cancel or limit that job.

## 2. How does the TaskExecutor run the consumers?

DMLC uses the Spring TaskExecutor to run the invokers. When the container starts, it creates the initial number of tasks according to concurrentConsumers. Each task manages the message-receiving loop and invokes the listener when a message arrives.

### 2.1. The default executor

If you do not pass an executor, DMLC creates a SimpleAsyncTaskExecutor:

~~~java
DefaultMessageListenerContainer container =
    new DefaultMessageListenerContainer();

container.setConcurrentConsumers(3);
~~~

With the configuration above, the container initializes three consumers and the corresponding listener tasks. SimpleAsyncTaskExecutor creates threads on demand; by default it uses platform threads and is not a traditional reusing pool.

A listener thread is usually occupied for the entire duration of the message-receiving task. This is simple and suits many standalone JMS applications. The number of listener threads can grow up to maxConcurrentConsumers if dynamic scaling is enabled.

### 2.2. Passing a dedicated executor

You can supply an application-managed executor:

~~~java
container.setTaskExecutor(jmsListenerExecutor);
~~~

This is useful when you need to integrate with a special thread-management environment or want to control the pool, thread names, and resource limits. However, an ordinary thread pool does not automatically make consumers lighter: if the listener task runs for a long time, each consumer still holds a thread during that time.

DMLC recognizes a SchedulingTaskExecutor that declares a preference for short-lived tasks. With this kind of executor, the container by default uses maxMessagesPerTask equal to 10 to end and reschedule the task after a number of receives. That gives the thread pool a chance to distribute threads to other work.

If you use an executor with a pool smaller than the maximum number of consumers, tasks may have to queue up or be rejected when the pool can no longer accept them. Coordinate the pool size, queue capacity, and maxConcurrentConsumers; monitor both the number of scheduled consumers and the number of active consumers.

### 2.3. Virtual threads on Java 21+

Since Spring Framework 6.2, DMLC has setVirtualThreads(true) to ask the default SimpleAsyncTaskExecutor to use virtual threads instead of platform threads:

~~~java
container.setVirtualThreads(true);
~~~

This option only applies when DMLC creates the default executor itself. If you have already passed in an external TaskExecutor, configure virtual threads directly on that executor. Virtual threads suit tasks that wait on I/O, but they do not replace limiting concurrency, managing JMS resources, or dealing with slow listeners.

## 3. receiveTimeout controls a single poll

DMLC inherits receiveTimeout from AbstractPollingMessageListenerContainer. The default value is 1000 milliseconds, i.e., one second.

~~~java
container.setReceiveTimeout(1_000L);
~~~

Each poll calls MessageConsumer.receive(timeout). The result can be:

| Timeout value | Behavior |
| --- | --- |
| A positive number, e.g. 1000 | Waits at most 1000 ms; if there is no message yet, receive returns null |
| 0 | Waits indefinitely; usually unsuitable because it can make the container hard to shut down cleanly |
| A negative number, e.g. -1 | Does not wait; corresponds to receiveNoWait() |

The timeout is measured in milliseconds. With a finite timeout, the container has a chance to return to the loop to check state, coordinate tasks, and run consumer-management logic.

If the container participates in a transaction, receiveTimeout needs to be smaller than the transaction timeout of the transaction manager. If receive waits longer than the transaction timeout, the transaction can expire while the consumer is still waiting for a message.

### 3.1. receiveTimeout is not a message processing timeout

Suppose the listener receives a message at 10:00:00 and processes it until 10:00:20. During those 20 seconds, the listener is working with the message; receiveTimeout does not limit this time. Only after processing finishes does the consumer return to calling receive to wait for the next message.

If you need to limit business processing time, set the timeout at the HTTP client, database call, service call, or the corresponding processing mechanism. Do not use receiveTimeout to control a long-running listener.

### 3.2. Choosing a timeout by goal

- A short timeout helps the consumer detect an empty queue quickly and react to the stop state sooner, but increases the number of polls.
- A long timeout reduces polling frequency when the queue is often empty, but can make idle detection and shutdown time longer.
- A timeout of 0 keeps the consumer in a single indefinite receive and is usually not recommended for DMLC.
- A negative timeout can create a non-waiting polling loop; only use it when you have clearly designed the run cadence and load limits.

There is no single value that suits every system. Choose the timeout based on the desired latency, the transaction timeout, the message cadence, and the polling cost of the JMS provider.

## 4. What is an idle consumer?

A receive is considered an idle receive when receiveTimeout has elapsed without a message, meaning the consumer got a null result.

DMLC uses this result to evaluate whether a surplus consumer should continue to exist. A consumer just created to handle increased load may keep receiving messages for a while. If the queue goes quiet again, the container can release that consumer and return to the base number of consumers.

You need to distinguish:

- **Core consumer:** within concurrentConsumers; the container keeps them until shutdown.
- **Surplus consumer:** a consumer created additionally during dynamic scaling; can be stopped when load decreases.
- **Idle receive:** one receive that times out without receiving a message.
- **Idle task execution:** one run of a task that did not receive a message, according to the task's limits.

The idle limits work together with receiveTimeout and maxMessagesPerTask to tune the speed of scale up/scale down.

## 5. Enabling dynamic scaling with concurrency

DMLC only automatically increases/decreases the number of consumers when maxConcurrentConsumers is greater than concurrentConsumers.

~~~java
container.setConcurrentConsumers(2);
container.setMaxConcurrentConsumers(8);
~~~

In this example:

- Two consumers are the minimum maintained.
- When queue load increases, DMLC can create additional consumers up to a maximum of eight.
- When load decreases, the surplus consumers can be stopped to return to the two base consumers.

By default concurrentConsumers and maxConcurrentConsumers are both 1, so dynamic scaling is not enabled unless maxConcurrentConsumers is changed.

### 5.1. Increasing consumers when messages arrive

When an invoker receives a message, DMLC can schedule an additional invoker if maxConcurrentConsumers has not been reached and the idleConsumerLimit allows it. idleConsumerLimit defaults to 1: the container only schedules an additional invoker if there is currently no idle invoker.

Increasing idleConsumerLimit can make the container expand more aggressively, because it allows creating additional invokers even when some consumers are still idle. This can speed up the ramp-up but can also create more consumers than needed.

### 5.2. Reducing consumers when the queue is quiet

When consecutive receives return null, DMLC marks the task as idle. If the task reaches idleTaskExecutionLimit, the surplus consumer ends and yields resources to the remaining consumers.

idleTaskExecutionLimit defaults to 1. Increasing this value helps keep consumers longer, avoiding continual scaling up and then down when load fluctuates.

## 6. The idle limits and defaults in Spring Framework 7.0.9

DMLC has many properties that control the task lifecycle. Do not confuse them with one another:

| Property | Default | Effect |
| --- | --- | --- |
| concurrentConsumers | 1 | The base number of consumers always kept |
| maxConcurrentConsumers | 1 | The maximum number of consumers; at 1 there is no dynamic scaling |
| receiveTimeout | 1000 ms | The maximum wait time of one receive |
| idleConsumerLimit | 1 | The number of idle consumers allowed when deciding to create an additional invoker |
| idleTaskExecutionLimit | 1 | The number of idle task executions before the task ends |
| idleReceivesPerTaskLimit | 10 with the default/simple executor | The number of consecutive receives returning null before a surplus consumer is marked idle |
| maxMessagesPerTask | -1 with an ordinary TaskExecutor; 10 with a SchedulingTaskExecutor that prefers short tasks | The maximum number of receive attempts in one task; a timed-out attempt also counts |

### 6.1. idleReceivesPerTaskLimit and consumer idle time

With the default executor SimpleAsyncTaskExecutor, DMLC sets the effective idleReceivesPerTaskLimit to 10 for surplus consumers. If receiveTimeout is the default 1000 ms, a surplus consumer can be scaled down after about ten consecutive receives with no message, i.e., about 10 seconds of idleness.

Example:

| receiveTimeout | idleReceivesPerTaskLimit | Estimated idle time |
| --- | --- | --- |
| 500 ms | 10 | About 5 seconds |
| 1000 ms | 10 | About 10 seconds |
| 2000 ms | 10 | About 20 seconds |

This is an estimate based on consecutive timed-out receives; the actual time also depends on task scheduling and provider latency.

This limit mainly applies to surplus consumers and does not reduce the number of core consumers in concurrentConsumers. Since Spring 6.2, when using an executor that prefers short tasks, idleReceivesPerTaskLimit only affects core consumers when combined with maxMessagesPerTask so that DMLC reschedules those tasks.

### 6.2. idleTaskExecutionLimit

idleTaskExecutionLimit determines how many idle executions are needed before the task ends. The default is 1, so a task that has been marked idle can end right away in the dynamic scaling mechanism.

Increase this value when consumers are created and stopped too often. Consumers will live longer after the queue goes quiet, in exchange for holding threads and JMS resources longer.

### 6.3. maxMessagesPerTask

The property name refers to the number of messages, but in practice it limits the number of receive attempts in one task. Receives that time out and return null are also counted.

With an ordinary TaskExecutor, the default is -1, meaning the task can run continuously until the container stops. With a SchedulingTaskExecutor that declares a preference for short tasks, the default is 10 so that the task ends and is rescheduled after at most ten receive attempts.

You can set the value explicitly:

~~~java
container.setMaxMessagesPerTask(10);
~~~

A value of about 10 to 100 is usually a starting point to balance the cost of rescheduling against the thread pool's ability to distribute work. A small value lets tasks return threads more often; a large value reduces context switching but holds threads longer.

## 7. Example DMLC configuration with a TaskExecutor and idle time

The following example configures a queue listener with two base consumers and at most eight consumers. ThreadPoolTaskExecutor is an executor dedicated to the listener; each task handles at most ten receive attempts and is then rescheduled.

~~~java
@Configuration
public class OrdersListenerConfiguration {

    @Bean
    public ThreadPoolTaskExecutor jmsListenerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("jms-orders-");
        return executor;
    }

    @Bean
    public DefaultMessageListenerContainer ordersContainer(
            ConnectionFactory connectionFactory,
            ThreadPoolTaskExecutor jmsListenerExecutor,
            MessageListener orderMessageListener) {

        DefaultMessageListenerContainer container =
            new DefaultMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);
        container.setDestinationName("orders.queue");
        container.setMessageListener(orderMessageListener);

        container.setConcurrentConsumers(2);
        container.setMaxConcurrentConsumers(8);

        container.setTaskExecutor(jmsListenerExecutor);
        container.setMaxMessagesPerTask(10);
        container.setReceiveTimeout(1_000L);
        container.setIdleTaskExecutionLimit(1);

        container.setSessionTransacted(true);
        return container;
    }
}
~~~

The ConnectionFactory and MessageListener components are supplied by the application. The ConnectionFactory must be able to connect to the JMS provider, and the queue orders.queue must exist or be allowed to be created dynamically by the provider.

ThreadPoolTaskExecutor has eight workers, corresponding to maxConcurrentConsumers equal to eight. A queue capacity of 32 allows rescheduled tasks to wait for a worker to become available. maxMessagesPerTask equal to 10 makes tasks end periodically so the pool can distribute threads.

Because the example uses a SchedulingTaskExecutor-style executor, DMLC by default can use maxMessagesPerTask equal to 10; the code sets it explicitly so the policy is easy to read and does not depend on an implicit default. With this kind of executor, each task can perform at most ten receive attempts, including the wait that times out at receiveTimeout.

This is a Spring JMS integration configuration, not a standalone program. To run it you need a JMS provider, a ConnectionFactory, a queue, and a configured MessageListener bean. There is no fixed stdout because the result depends on the actual messages in the broker.

## 8. When to keep consumers longer or scale down faster?

| Scenario | Suggested adjustment | Impact |
| --- | --- | --- |
| A queue with even load | Keep concurrentConsumers appropriate and maxConcurrentConsumers close to the expected load | Avoids creating/stopping consumers often |
| Load rising in bursts | Give a higher maxConcurrentConsumers and consider idleConsumerLimit | Speeds up creating consumers when messages arrive |
| Load dropping quickly after a burst | Lower receiveTimeout or idleReceivesPerTaskLimit | Surplus consumers are marked idle sooner |
| Load fluctuating continuously | Increase idleTaskExecutionLimit or idleReceivesPerTaskLimit | Keeps consumers longer, reduces churn |
| A thread pool that needs to share workers | Use a SchedulingTaskExecutor and set a reasonable maxMessagesPerTask | Tasks end periodically so the pool redistributes |
| A queue with few messages | Keep concurrency low | Reduces idle threads and sessions |
| A listener that processes slowly | Adjust concurrency according to processing time and broker capability | Avoids the message backlog growing too fast |

Do not increase concurrency just to reduce queue depth. If the listener processes slowly because of the database or an external service, adding consumers can overload the dependent system.

## 9. Queue, topic, and processing order

Dynamic scaling mainly suits queues. Multiple consumers reading the same queue share the load; a message is delivered to one suitable consumer.

With a topic, multiple consumers on the same node in an ordinary configuration may receive the same copy of a message. Therefore, you usually keep one consumer for a topic, unless the broker supports shared subscription and the application has been configured correctly per the provider.

When you increase the number of consumers on a queue, the global processing order is no longer guaranteed. Two messages delivered to two consumers can complete in a different order. If the business requires ordering per order, account, or partition, design a partition key or a dedicated serialization mechanism.

## 10. receiveTimeout, transactions, and shutdown

receiveTimeout must be smaller than the transaction timeout if the container is participating in a transaction. If the transaction timeout is 30 seconds, do not let a single receive wait longer than that.

A timeout of 0 means waiting indefinitely. This can make the container hard to shut down cleanly because the thread is blocked in receive. A negative value performs a non-waiting receive and can make the polling loop run too often if there is no throttling mechanism.

For a listener that needs reliability, configure sessionTransacted or an appropriate transaction manager. When the listener throws an exception in a local JMS transaction, the transaction can roll back and the broker can redeliver the message according to the provider's policy. The consumer should still be idempotent because duplicates can occur in some edge cases.

## 11. Monitoring consumers and investigating problems

DMLC provides useful observation methods:

- getConcurrentConsumers(): the configured base number of consumers.
- getMaxConcurrentConsumers(): the maximum consumer limit.
- getScheduledConsumerCount(): the number of consumer tasks that have been scheduled.
- getActiveConsumerCount(): the number of consumers that are active.
- isRecovering(): whether the container is in the process of recovering the connection.

The scheduled consumer count can be higher than the active consumer count because a task has been scheduled but is not yet running. Read these metrics together with queue depth, the rate of incoming messages, listener processing time, and the number of broker reconnects.

If active consumers frequently hit maxConcurrentConsumers while the backlog keeps growing, check the listener processing time, the database throughput, and broker limits. If consumers keep increasing and then decreasing, look at receiveTimeout, idleReceivesPerTaskLimit, idleTaskExecutionLimit, and the message cadence.

## 12. Common mistakes

| Symptom | Cause | Remedy |
| --- | --- | --- |
| Only one consumer even though you want to scale | maxConcurrentConsumers is still equal to concurrentConsumers | Set maxConcurrentConsumers higher than the minimum |
| Surplus consumers disappear too quickly | idleReceivesPerTaskLimit or idleTaskExecutionLimit is low | Increase the idle limits if load often returns |
| Consumers hold threads for a long time when the queue is empty | A long receiveTimeout or a large maxMessagesPerTask | Lower the timeout or the number of attempts in one task |
| The thread pool does not run all the consumers | The pool is smaller than concurrency or tasks occupy threads for a long time | Increase the pool appropriately or use a SchedulingTaskExecutor with short tasks |
| Tasks are rejected when scaling | The pool is out of workers and the queue is full | Check the queue capacity, max pool size, and concurrency |
| A topic consumer receives repeated messages | Multiple consumers of the same subscription without an appropriate shared subscription | Keep one consumer or configure a shared subscription per the provider |
| Messages complete out of order | Multiple consumers process concurrently | Keep concurrency at 1 or design a partition/sequence |
| Shutdown is slow | receiveTimeout equal to 0 or a listener that processes for too long | Use a finite timeout and control processing time |
| CPU rises when the queue is empty | A negative receiveTimeout creates non-waiting polling too often | Use a finite timeout and measure the polling cost |

## 13. Configuration checklist

- [ ] Determine whether it is a queue or a topic before increasing concurrency.
- [ ] Choose concurrentConsumers as the minimum consumer level that must be maintained.
- [ ] Only enable dynamic scaling when maxConcurrentConsumers is greater than concurrentConsumers.
- [ ] Choose the TaskExecutor according to a long-lived task or short-lived task model.
- [ ] If using a pool, ensure the pool and queue can accommodate the maximum number of consumers.
- [ ] Set receiveTimeout smaller than the transaction timeout and suited to the desired latency.
- [ ] Understand clearly that a timeout of 0 means wait indefinitely and a negative value means no-wait.
- [ ] Distinguish idleReceivesPerTaskLimit, idleTaskExecutionLimit, and maxMessagesPerTask.
- [ ] Monitor the active/scheduled consumer counts and the queue backlog.
- [ ] Test load increase, load decrease, broker restart, slow listeners, and shutdown.
- [ ] Configure transactions/acknowledgement and design idempotent consumers when reliability is needed.

## 14. References

- [Spring Framework API — DefaultMessageListenerContainer 7.0.9](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
- [Spring Framework API — AbstractPollingMessageListenerContainer 7.0.9](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html)
- [Spring Framework API — TaskExecutor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework API — SchedulingTaskExecutor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/scheduling/SchedulingTaskExecutor.html)
- [Spring Framework API — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Spring Framework — Receiving a Message](https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html)
