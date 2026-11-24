# Listener task executor in Spring Kafka

In Spring Kafka, the **listener task executor** is the `TaskExecutor` that the listener container uses to run consumer threads. Each consumer thread executes the poll loop, delivers records to the listener, handles acknowledgments, and continues polling. The executor determines which thread runs that loop, how threads are named, and how threads are allocated when there are multiple listener containers.

The name `listenerTaskExecutor` can lead readers to think that this executor creates a new thread for each `@KafkaListener` invocation. That is not its role. In modern Spring Kafka, the executor is used to run the container's long-lived consumer threads. Listeners are typically invoked sequentially on their respective consumer threads.

Proper executor configuration helps the application start enough consumers, avoid thread starvation when scaling concurrency, and make logs easy to trace. Misconfiguration can prevent some containers from starting, leave consumers waiting in a thread pool queue, or prolong shutdown.

## 1. Where does the task executor sit in the architecture?

Spring Kafka provides listener containers to manage the lifecycle of Kafka consumers. With `@KafkaListener`, endpoints are registered with `KafkaListenerEndpointRegistry`; containers are created from `ConcurrentKafkaListenerContainerFactory` or an equivalent factory.

~~~text
Spring Application
       |
       v
KafkaListenerEndpointRegistry
       |
       v
ConcurrentMessageListenerContainer
       |
       +--> child container 1
       |       |
       |       +--> Kafka consumer 1
       |       +--> consumer thread 1
       |                 |
       |                 +--> poll()
       |                 +--> invoke @KafkaListener
       |                 +--> acknowledgement / commit
       |
       +--> child container 2
       |       |
       |       +--> Kafka consumer 2
       |       +--> consumer thread 2
       |                 |
       |                 +--> poll()
       |                 +--> invoke @KafkaListener
       |                 +--> acknowledgement / commit
       |
       +--> child container 3
               |
               +--> Kafka consumer 3
               +--> consumer thread 3
                         |
                         +--> poll()
                         +--> invoke @KafkaListener
                         +--> acknowledgement / commit

             Listener task executor
             provides threads for the consumers
~~~

With `KafkaMessageListenerContainer`, there is typically one consumer and one consumer thread. With `ConcurrentMessageListenerContainer`, the parent container manages multiple child containers; each child has its own consumer and requires a thread to run.

`ContainerProperties` holds the executor configuration via `listenerTaskExecutor`. The default executor is `SimpleAsyncTaskExecutor`. If custom pool control or thread naming is not required, applications can usually use the default.

## 2. What does this executor actually run?

A consumer thread executes a long-running loop for the entire time the container is running:

1. Call `KafkaConsumer.poll()` to fetch records.
2. Pass records to the listener adapter.
3. Invoke the `@KafkaListener` method.
4. Handle acknowledgments, offset commits, or transactions per container configuration.
5. Continue polling until the container is stopped.

Therefore, an executor thread is typically occupied by one consumer for the entire running lifecycle of that consumer. This is a crucial difference from an executor handling short-lived tasks, where a thread picks up a task, finishes it, and returns to the pool.

### The executor does not create a thread per record

Suppose a listener has concurrency 3 and is processing thousands of records. The container does not need to create thousands of threads. It uses three consumer threads; each thread sequentially processes records assigned to its corresponding consumer.

~~~text
Consumer thread 1: poll -> record A -> listener -> poll -> record D -> listener
Consumer thread 2: poll -> record B -> listener -> poll -> record E -> listener
Consumer thread 3: poll -> record C -> listener -> poll -> record F -> listener
~~~

If you need more consumers processing in parallel, adjust concurrency and partition counts. Changing the task executor to a larger pool by itself does not increase the number of consumers or partitions being processed.

### Not an executor for offloading business logic

`listenerTaskExecutor` is not a separate worker pool where the listener dispatches each record to another thread and returns immediately. Manually offloading processing to another executor can alter completion order, acknowledgment timing, and offset commits.

If asynchronous processing is needed, use the async listener mechanism supported by your Spring Kafka version or explicitly design manual acknowledgments, processing order, and error handling. Do not share a Kafka `Consumer` across threads to call `poll`, `seek`, `commit`, or arbitrary consumer APIs; Kafka consumers are not thread-safe and are managed by the container on the consumer thread.

## 3. Declaring the listener task executor in ContainerProperties

The executor property is configured on `ContainerProperties`:

~~~java
factory.getContainerProperties()
        .setListenerTaskExecutor(listenerTaskExecutor);
~~~

The `setListenerTaskExecutor(AsyncTaskExecutor)` API has been provided since Spring Kafka 2.8.9. The older `setConsumerTaskExecutor(AsyncListenableTaskExecutor)` API was deprecated in favor of `setListenerTaskExecutor`.

When reading version-specific docs or source code, you may encounter older names such as `consumerTaskExecutor` or `consumerExecutor`. Use the API supported by your project's actual dependency; in modern Spring Kafka, prefer `setListenerTaskExecutor`.

The executor is a Spring Framework setting, not a Kafka consumer property like `max.poll.records` or `max.poll.interval.ms`. Therefore, do not put it in `spring.kafka.consumer.properties`. Inject the executor into the container factory and attach it to `ContainerProperties`.

## 4. Default executor: SimpleAsyncTaskExecutor

If the application does not supply a custom executor, Spring Kafka uses `SimpleAsyncTaskExecutor` for consumer threads.

Operational characteristics to understand:

- The executor creates a thread to run a task when the container needs to start a consumer.
- Default thread names follow a pattern tied to the bean name and consumer index, such as `ordersListener-0-C-1`.
- With concurrent containers, each child container has a distinct identifier in its thread name.
- `SimpleAsyncTaskExecutor` is not a thread-reusing pool like `ThreadPoolTaskExecutor`.
- The default can be used when listener counts and concurrency are moderate, but large applications often want clearer control over thread counts and thread names.

Do not assume that `SimpleAsyncTaskExecutor` automatically caps threads by CPU count. The number of running consumers primarily comes from the configured number of containers and concurrency. If resource limits are needed, configure a bounded executor and ensure enough threads for all required consumers.

## 5. Using ThreadPoolTaskExecutor for consumer threads

`ThreadPoolTaskExecutor` is the choice when you want centralized management of thread count, thread name prefixes, and allocation policies.

The example below creates a fixed pool of three threads for a listener container with concurrency 3:

~~~java
@Configuration
public class KafkaListenerExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor kafkaListenerTaskExecutor() {
        var executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(3);
        executor.setQueueCapacity(0);
        executor.setThreadNamePrefix("orders-consumer-");

        return executor;
    }

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    orderListenerContainerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory,
            ThreadPoolTaskExecutor kafkaListenerTaskExecutor) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<
                        String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
                .setListenerTaskExecutor(kafkaListenerTaskExecutor);

        return factory;
    }
}
~~~

Here:

- `corePoolSize=3` keeps three base threads.
- `maxPoolSize=3` caps total pool threads at three.
- `queueCapacity=0` uses direct handoff instead of queuing consumer tasks in a long queue.
- `threadNamePrefix` helps identify consumer threads in logs and thread dumps.
- `setConcurrency(3)` creates three child containers requiring three consumer threads.
- `setListenerTaskExecutor` binds the pool to consumers created by the factory.

The `ThreadPoolTaskExecutor` bean has its lifecycle and initialization managed by Spring. In real applications, name beans clearly and use `@Qualifier` if multiple executors of the same type exist.

If configured child containers exceed the threads available for allocation, some consumer tasks may be rejected or wait in the queue. The container has a `consumerStartTimeout` property to wait for the consumer thread to start before logging a warning; modern defaults are typically 30 seconds. Check startup logs and events if consumers fail to start on time.

## 6. Calculating how many threads to allocate

For consumer tasks, calculate based on the total number of running consumers, not just the number of listener methods.

Simple planning formula:

~~~text
Required consumer threads
    = sum of concurrency across running listener containers
      sharing the executor
~~~

Example:

| Listener container | Concurrency | Consumer threads needed |
|---|---:|---:|
| ordersListener | 3 | 3 |
| paymentsListener | 2 | 2 |
| inventoryListener | 1 | 1 |
| **Total** | **6** | **6** |

If all three containers share one executor, the pool needs at least six threads so all six consumers can run concurrently.

Do not count only one factory if the application has multiple `@KafkaListener` endpoints or multiple factories sharing an executor. Also include dynamically created containers if they use the same pool.

### Concurrency greater than partition count

If a topic has two partitions but listener concurrency is set to five, Spring may create five child consumers; only two consumers can be assigned partitions in the group in steady state, and the remaining consumers have no partitions to process.

Nevertheless, each child container is still a consumer task and needs a thread to run. Therefore, when sizing the executor, use the configured concurrency and actual container count, not just the number of currently assigned partitions.

Increasing concurrency beyond partition count may not increase throughput while still consuming threads and consumer connections. Choose concurrency based on partition count, dependency processing capacity, and throughput targets.

## 7. Why does thread pool queue capacity matter?

`ThreadPoolTaskExecutor` normally works in this order: use core threads first, then place tasks in the queue; only when the queue is full does it expand up to max pool size.

For consumer tasks, this warrants attention because tasks usually live as long as the container. If the queue is large, new consumer tasks may sit waiting in the queue while running threads are occupied long-term by other consumers.

For example, a pool has core size two, max size six, and queue capacity one hundred. Once two consumer tasks occupy the two core threads, subsequent consumer tasks may get queued. The pool will not necessarily expand to six right away because the queue is not full.

For consumers that need to start concurrently, usually choose one of two approaches:

- A fixed pool with threads equal to total consumers needed, with a small or zero queue.
- A clearly bounded pool with an intentionally designed queue/rejection policy that ensures all required consumers can start.

Do not set an unbounded queue and assume `maxPoolSize` will automatically expand the pool. Also do not choose `CallerRunsPolicy` arbitrarily: a consumer task could run on the thread calling start, blocking container startup or changing the execution thread unexpectedly.

## 8. Sharing an executor across multiple listener containers

An executor can be shared across multiple factories or containers for centralized thread management. When doing so, size it for the total concurrency of all containers sharing the pool.

Example of two factories:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        @Qualifier("kafkaListenerTaskExecutor")
        ThreadPoolTaskExecutor executor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setListenerTaskExecutor(executor);

    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
paymentsFactory(
        ConsumerFactory<String, PaymentEvent> consumerFactory,
        @Qualifier("kafkaListenerTaskExecutor")
        ThreadPoolTaskExecutor executor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, PaymentEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(2);
    factory.getContainerProperties().setListenerTaskExecutor(executor);

    return factory;
}
~~~

The shared pool needs at least five consumer threads if both listeners run concurrently and no other containers use the pool.

If the pool has only three threads, `orders` may claim all threads before `payments` starts. That can prevent `payments` from getting a consumer thread within `consumerStartTimeout`.

### When to use separate executors?

Dedicated executors per listener group help:

- Cap resources per group.
- Prevent a high-concurrency listener from taking all threads from another group.
- Set distinct thread name prefixes for observability.
- Tune capacity independently based on load and criticality.

On the flip side, multiple pools increase total thread count and require more lifecycle management. Split pools when there is a resource isolation or operational reason, not merely because each listener has a different name.

## 9. How are listener task executor and concurrency related?

`concurrency` determines how many child consumer containers a `ConcurrentMessageListenerContainer` manages. The executor provides threads for those child consumers to run.

The two settings work together:

~~~text
factory.setConcurrency(4)
             |
             v
Creates 4 child consumer containers
             |
             v
Each child needs 1 consumer thread
             |
             v
listenerTaskExecutor must supply 4 threads
~~~

Example:

~~~java
factory.setConcurrency(4);
factory.getContainerProperties()
        .setListenerTaskExecutor(kafkaListenerTaskExecutor);
~~~

If the executor has four threads available, four consumers can run. If it only has two threads and no room for the remaining tasks to execute, the other two consumers cannot start on time.

Increasing pool size without increasing concurrency does not give the listener more consumers. Conversely, increasing concurrency without increasing thread allocation capacity can prevent some child containers from starting.

Effective concurrency is also bounded by assigned partitions. If there are four consumers but the topic has only two partitions, you cannot achieve four consumers processing partitions independently in the same group.

## 10. Distinguishing listener task executor from other executors

A Spring application may have many kinds of executors. Do not use them interchangeably without considering lifecycle and purpose.

| Component | Purpose | Task lifecycle |
|---|---|---|
| `listenerTaskExecutor` | Runs listener container consumer threads | Long-lived tasks, typically lasting for the container's runtime |
| `@Async` executor | Runs asynchronous application methods | Short or long business tasks depending on application |
| `TaskScheduler` | Runs scheduled jobs and monitor tasks | Periodic or timed tasks |
| `CompletableFuture` executor | Runs callbacks or async computations | Per-completion tasks |
| Application-created producer callback executor | Runs logic after producer send completes | Per-send tasks |

Do not share a small pool between consumer threads and HTTP tasks or short background jobs. Consumer tasks hold threads long-term; if business tasks occupy the pool, consumers may fail to start or have no thread to continue polling.

Similarly, do not configure a pool with dozens of consumer threads just to satisfy `@Async` needs. Separate resources by workload type.

## 11. Do not offload KafkaConsumer across multiple threads

Kafka `Consumer` is not thread-safe. Spring Kafka containers ensure the consumer is used on its managed thread. `listenerTaskExecutor` only provides threads for the container to run the consumer loop.

Do not do the following:

~~~java
@KafkaListener(topics = "orders")
public void onOrder(
        ConsumerRecord<String, OrderCreated> record,
        Consumer<?, ?> consumer) {

    businessExecutor.execute(() -> {
        // Do not call consumer.seek(), poll(), commitSync(), or
        // other Consumer APIs from this thread.
        process(record.value());
    });
}
~~~

The snippet above illustrates a dangerous boundary. Such offloading also creates another issue: the listener returns before business processing completes, so the container may commit the offset while side effects have not yet succeeded. If `process` fails, the record may already be considered processed.

If asynchronous processing is needed, use the async listener API supported by your Spring Kafka version or design manual acknowledgment and `asyncAcks` with a clear understanding of offset ordering, pausing, and recovery. Do not pass the Kafka `Consumer` object to business threads.

## 12. Thread naming and diagnostics

Thread names help distinguish consumers in logs and thread dumps. By default, Spring Kafka generates names linked to the bean name and child container. When using a custom executor, you can set a prefix:

~~~java
executor.setThreadNamePrefix("orders-consumer-");
~~~

Logs may show:

~~~text
orders-consumer-1
orders-consumer-2
orders-consumer-3
~~~

If multiple listeners share a pool, a shared thread name prefix does not tell you which container a thread is running at every moment. Combine thread names with logged listener ID, group ID, client ID, topic, partition, and offset.

Since Spring Kafka 3.0.1, the container supports customizing consumer thread names via `changeConsumerThreadName` and `threadNameSupplier`. This is a container thread-naming feature; it does not change thread count or executor allocation mechanics.

Operational signals to monitor:

- `ConsumerFailedToStartEvent`: consumer failed to start within `consumerStartTimeout`; one possible cause is an executor lacking threads.
- Consumer start timeout warning logs.
- Pool size, active thread count, and task rejections of `ThreadPoolTaskExecutor`.
- Number of consumers actually started and assigned partitions.
- Consumer lag, poll latency, and listener processing time.
- Thread dumps when consumers stop polling or containers fail to stop.

You can listen to events to detect consumers failing to start:

~~~java
@Component
public class KafkaConsumerLifecycleMonitor {

    @EventListener
    public void onConsumerFailedToStart(
            ConsumerFailedToStartEvent event) {
        log.error(
                "Kafka consumer failed to start; check task executor capacity: {}",
                event.getSource()
        );
    }
}
~~~

Event types and getter APIs may vary by version. Use the event classes from the Spring Kafka version your application uses.

## 13. Shutdown and executor lifecycle

Consumer threads typically run until the listener container stops. Therefore, the executor must remain active while containers need to start, poll, and shut down.

A sound shutdown sequence:

~~~text
Application begins shutdown
          |
          v
Stop accepting new work
          |
          v
Stop listener containers
          |
          v
Containers close Kafka consumers
          |
          v
Consumer tasks terminate
          |
          v
Executor is shut down via Spring lifecycle
~~~

If the executor is shut down before containers stop, containers may fail to restart or obtain needed threads. Let Spring manage bean lifecycle and ensure the stop order between listener containers and executors fits the application.

Do not manually call `shutdown()` on a shared executor while a listener is still running. If an executor serves multiple containers, close it only after all dependent containers have stopped.

When an application redeploys or stops while a listener is processing a record, uncommitted offsets may cause the record to be redelivered later. The executor does not decide commit semantics; acknowledgment mode, transactions, and error handlers control that. Listeners still need to be idempotent if business operations can experience redelivery.

## 14. Spring Boot configuration and custom factories

Spring Boot provides properties for listeners such as concurrency, ack mode, and poll timeout. However, a custom `TaskExecutor` is a Spring bean, not a simple Kafka client property to put in YAML.

Example YAML configuring concurrency:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders
      enable-auto-commit: false
    listener:
      concurrency: 3
      ack-mode: record
~~~

Then configure the executor on the factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
kafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory,
        @Qualifier("kafkaListenerTaskExecutor")
        ThreadPoolTaskExecutor executor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderCreated>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(3);
    factory.getContainerProperties().setListenerTaskExecutor(executor);

    return factory;
}
~~~

If you want to use Spring Boot's auto-configured factory, customize the factory bean using the configuration mechanism of your Boot version. When an application has multiple listeners, clearly verify which listener uses which factory to avoid configuring an executor on a factory unused by the endpoint.

## 15. Common mistakes

**Pool has fewer threads than total concurrency**

Some consumer tasks get queued or rejected. Containers may log consumer start timeout warnings. Calculate total concurrency across all containers sharing the executor.

**Queue is too large**

New consumer tasks wait in the queue because threads are running long-lived consumers. The pool does not expand as expected because the queue is not full. For consumer tasks, design the pool around the number of threads needed concurrently.

**Sharing a pool with @Async or HTTP tasks**

Short tasks can occupy threads needed by consumers. Separate pools or size for total workload and priority.

**Increasing executor size without increasing concurrency**

Consumer count does not change. The pool may simply sit with many idle threads.

**Increasing concurrency beyond partition count**

Some consumers receive no partitions, so throughput does not increase correspondingly while still consuming threads and consumer connections.

**Mistaking the executor for a listener parallelization mechanism**

One consumer thread typically invokes the listener sequentially. Asynchronous processing requires appropriate APIs and acknowledgment semantics, not just swapping the executor.

**Using Kafka Consumer directly from another thread**

Can cause thread-safety bugs and violate container ownership of the consumer. Let the container manage consumer APIs.

**Shutting down the executor while containers are still running**

Containers lose threads needed to poll or restart. Stop containers before closing the executor.

**Using deprecated APIs**

`setConsumerTaskExecutor` was deprecated in favor of `setListenerTaskExecutor`. Check your Spring Kafka version and use the appropriate API.

## 16. Executor sizing procedure for production

1. List all running listener containers and the factory each listener uses.
2. Record the concurrency of each container.
3. Group containers by shared executor.
4. Sum the concurrency within each group.
5. Configure core/max pool size sufficient for the consumers needing to run concurrently.
6. Choose queue capacity deliberately; avoid unbounded queues for long-lived tasks.
7. Set distinct thread name prefixes for observability.
8. Start the application and confirm every consumer started.
9. Check partition assignments to confirm concurrency yields actual throughput.
10. Inspect pool metrics, consumer lag, and processing times under increased load.
11. Test shutdown/restart to confirm containers stop before the executor.
12. Check logs for consumer start timeouts and task rejections when capacity is insufficient.

For example, if two listeners with concurrency four and two share one pool, start with six consumer threads. Then verify load and partition counts to confirm concurrency is effective. Do not size the pool solely based on CPU count; consumer threads often wait on I/O and run poll loops, while throughput depends on partitions, brokers, listener latency, and dependencies.

## 17. Configuration checklist

- Confirmed `listenerTaskExecutor` runs container consumer threads.
- Distinguished this executor from pools processing individual business tasks.
- Used `setListenerTaskExecutor(AsyncTaskExecutor)` on supported versions.
- Calculated total concurrency of all containers sharing the pool.
- Pool has enough threads for concurrent consumer tasks.
- Queue capacity and rejection policy are chosen deliberately.
- Small pools are not shared with HTTP tasks, `@Async`, or unrelated callbacks.
- Kafka Consumer is not accessed from other threads.
- Verified partition counts and effective concurrency.
- Thread names help identify consumers in logs.
- Monitored consumer start timeouts, task rejections, active threads, and consumer lag.
- Executor remains alive while containers are active.
- Containers stop before the executor is shut down.
- Tested startup, shutdown, and restart of the application.

The listener task executor is the mechanism that supplies threads for consumer loops managed by Spring Kafka containers. Size it according to concurrent consumer count, keep the executor adequately provisioned throughout the lifecycle, and separate it from business-processing worker pools. Understanding this boundary makes tuning concurrency, monitoring consumers, and operating shutdowns predictable.

## References

- [Spring Kafka — Listener Container Properties](https://docs.spring.io/spring-kafka/reference/kafka/container-props.html)
- [Spring Kafka 3.2 — ContainerProperties API](https://docs.spring.io/spring-kafka/docs/3.2.10/api/org/springframework/kafka/listener/ContainerProperties.html)
- [Spring Kafka — Application Events](https://docs.spring.io/spring-kafka/reference/kafka/events.html)
