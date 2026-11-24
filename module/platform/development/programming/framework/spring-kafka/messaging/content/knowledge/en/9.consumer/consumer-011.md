# Closing a Consumer Safely

A Kafka consumer typically runs continuously in the background to receive and process events. When an application needs to stop—for example, when deploying a new version, scaling down pods, or shutting down a service—the consumer must terminate in a controlled manner. The goal is to stop accepting new work, allow in-flight processing a chance to complete, commit offsets according to configuration, and close the consumer connection properly.

With Spring Kafka, `@KafkaListener` is managed by a listener container. The container owns the lifecycle of the Kafka consumer, including polling, dispatching records, committing offsets, and closing the consumer. Therefore, the application should stop the container through the Spring lifecycle or `KafkaListenerEndpointRegistry`, rather than calling `KafkaConsumer.close()` directly on a container-managed consumer.

## 1. Why close a consumer safely?

When a process is terminated abruptly while processing records, two common situations occur:

- The record was processed, but the offset was not committed yet. When the partition is assigned to another consumer, the record may be read and processed again.
- The offset was committed before business processing completed. The new consumer may resume from the position after that record, causing unfinished work to be skipped.

Closing a consumer safely reduces the likelihood of these scenarios by coordinating shutdown timing, listener completion, and commits. However, graceful shutdown does not by itself create exactly-once semantics for every side effect. If the listener writes to a database, calls an API, or performs external operations outside Kafka, business logic still needs appropriate transactions or idempotency to tolerate reprocessing.

For example, a consumer processing `OrderPaid`:

```text
Application receives stop signal
          |
          v
Stop accepting new work / stop listener container
          |
          v
Finish running listener and remaining work per configuration
          |
          v
Commit offset or complete transaction if processing succeeds
          |
          v
Close KafkaConsumer and leave consumer group
          |
          v
Spring context shuts down
```

When a consumer leaves the group, Kafka redistributes its partitions to the remaining active consumers. This is normal behavior during shutdown; the goal is for that handover to happen after the container has stopped in a controlled fashion.

## 2. Spring Kafka manages the listener container lifecycle

When `@KafkaListener` is declared, Spring creates a listener endpoint and registers the corresponding container in `KafkaListenerEndpointRegistry`. The container manages one or more Kafka consumers depending on concurrency and partition assignment configuration.

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {

    @KafkaListener(
            id = "orders-listener",
            topics = "orders.events",
            groupId = "order-projection"
    )
    public void consume(String payload) {
        processOrderEvent(payload);
    }

    private void processOrderEvent(String payload) {
        // Process the order event.
    }
}
```

`id` is the identifier of the listener endpoint in the registry. You can use this ID to look up the container and control its lifecycle when the application needs to stop a specific listener, such as temporarily stopping an ingestion stream during maintenance.

Normally, Spring manages the listener container lifecycle alongside the `ApplicationContext`. When the context closes normally, containers are instructed to stop and close their Kafka consumers. If the application does not need to stop a listener independently, the default lifecycle mechanism is usually sufficient; there is no need to write a custom `@PreDestroy` to close the Kafka consumer a second time.

## 3. Stopping a listener via KafkaListenerEndpointRegistry

When you need to proactively stop a listener before the entire application shuts down, inject `KafkaListenerEndpointRegistry`, look up the container by ID, and call `stop()`.

```java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
class KafkaListenerControlService {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaListenerControlService.class);

    private final KafkaListenerEndpointRegistry registry;

    KafkaListenerControlService(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void stopOrdersListener() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container == null || !container.isRunning()) {
            return;
        }

        container.stop();
    }
}
```

`stop()` requests the container to terminate and waits for the stop process according to the container's lifecycle. You can use the `stop(Runnable callback)` overload if you need to execute an action after the container has stopped:

```java
container.stop(() -> log.info("orders-listener stopped"));
```

Control code should run from a management or dedicated control thread. Never call `KafkaConsumer.close()` directly from a listener or another thread, because `KafkaConsumer` is not designed for arbitrary multithreaded operations. The listener container owns the consumer and must coordinate shutdown.

If the application only wants to pause receiving records temporarily while retaining the container and partition assignment, consider the listener container's `pause()`/`resume()`. `pause()` is not equivalent to shutdown: the container keeps running, the consumer stays in the group and can keep polling, yet paused partitions do not deliver new records to the listener under the pause mechanism. `stop()` terminates the container, closes the consumer, and triggers partition reassignment.

## 4. What happens to in-flight records?

When a stop request arrives while a listener is executing, the container must coordinate with the consumer thread. A synchronously executing listener is usually allowed to run until it returns; afterward, the container completes the appropriate commit operations and closes the consumer. With a record listener, one poll may already have fetched multiple records. The container may still have remaining records from that poll to process before stopping, depending on the stop mode and Spring Kafka version.

Therefore, design listeners with bounded processing times. A listener that hangs on an HTTP call, database query, or lock wait can prolong the shutdown process. Set timeouts on dependencies and avoid unbounded blocking operations.

### Committing offsets per acknowledgment mode

Spring Kafka manages commit timing based on the acknowledgment mode. With `AckMode.BATCH`, the container typically commits offsets after finishing all records received from one poll. If the listener processes successfully and the container has a chance to commit before closing the consumer, the group can resume from the next position.

If using manual acknowledgment, only call `acknowledge()` after business work is complete:

```java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.stereotype.Component;

@Component
class ManualAckOrderListener {

    @KafkaListener(
            id = "manual-orders-listener",
            topics = "orders.events",
            groupId = "order-manual-projection"
    )
    public void consume(
            ConsumerRecord<String, String> record,
            Acknowledgment acknowledgment
    ) {
        processAndPersist(record.value());
        acknowledgment.acknowledge();
    }

    private void processAndPersist(String payload) {
        // Complete business work before acknowledging.
    }
}
```

The listener above must be configured with an appropriate manual acknowledgment mode, such as `MANUAL` or `MANUAL_IMMEDIATE`. If the application stops before acknowledging and the offset has not been committed, the record may be redelivered. This behavior must be handled safely using idempotency or appropriate transactions.

Do not commit offsets before business writes succeed. If you need to coordinate offset commits with other Kafka operations, use Kafka transactions and the proper transaction manager. A Kafka transaction does not automatically encompass external databases or HTTP services without a dedicated coordination mechanism.

## 5. Configuring shutdown timeouts

Spring Kafka has a shutdown timeout for listener containers. With Spring Boot, this duration can be configured in `application.yml`. You should also configure the timeout per shutdown phase of the Spring lifecycle:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: batch
      shutdown-timeout: 30s
  lifecycle:
    timeout-per-shutdown-phase: 40s

server:
  shutdown: graceful
```

Meaning:

- `enable-auto-commit: false`: lets the listener container manage offset commits according to the acknowledgment mode.
- `listener.ack-mode: batch`: commits in batches after successfully processing records received from a poll.
- `listener.shutdown-timeout: 30s`: duration the container waits for consumer termination according to Spring Kafka configuration.
- `lifecycle.timeout-per-shutdown-phase: 40s`: maximum duration Spring waits for each phase when closing the context.
- `server.shutdown: graceful`: if the application has a web server, instructs it to stop accepting new requests and allow in-flight requests to complete per the server's graceful shutdown mechanism.

The values above are only examples. Choose timeouts based on actual processing time and your Spring Boot/Spring Kafka version. The listener container wait time, the Spring lifecycle wait time, and the grace period granted by the platform before killing the process are distinct limits; outer limits must be large enough for inner steps to finish.

For example, if Kubernetes sends `SIGTERM` and gives the pod only 30 seconds before sending `SIGKILL`, configuring Spring to wait 40 seconds cannot guarantee the listener gets 40 seconds. The pod's `terminationGracePeriodSeconds` must exceed the total time needed to stop accepting requests, finish running listeners, and complete other application shutdown steps.

## 6. Shutdown sequence for a real application

A deployment shutdown sequence can be structured as follows:

1. Mark the instance as no longer ready to receive new requests. For web applications, the readiness probe must reflect the shutting-down state.
2. Stop accepting new work from external sources, such as APIs or schedulers that trigger processing.
3. Request listener containers to stop. Spring can do this when the `ApplicationContext` closes; if you need to stop early proactively, use `KafkaListenerEndpointRegistry`.
4. Let running listeners finish within the allotted wait time. Every database or external service call needs a timeout.
5. Let the container commit offsets or complete transactions according to the acknowledgment mode and transaction configuration.
6. Close the consumer, leave the consumer group, and let Kafka redistribute partitions.
7. Finalize remaining beans and resources, then terminate the process.

The exact sequence depends on the application architecture. If a listener needs another bean to finish processing, that bean must stay alive while the listener is stopping. Avoid closing connection pools or dependent clients before the listener container has finished stopping.

## 7. Retries, errors, and reprocessing capability

Graceful shutdown does not guarantee that no record will ever be reprocessed. For example, a listener already wrote data to the database, but the process stopped before committing the offset. Another consumer may re-read the record. If reprocessing writes the exact same change again, data can be duplicated unless business logic is idempotent.

Measures to handle this situation include:

- Use an event ID or unique business key to detect already-processed events.
- Use upserts or unique constraints in the database where appropriate.
- Acknowledge/commit only after the corresponding work has completed.
- Configure retries and dead-lettering per error policy; do not retry an unrecoverable error indefinitely during shutdown.
- If using transactions, clearly define which resources the transaction spans and how rollbacks are handled.

When shutdown occurs during a retry or backoff, shutdown duration is also affected. Choose bounded backoffs, dependency timeouts, and reasonable shutdown durations. If processing cannot finish in time, letting uncommitted records be redelivered is usually safer than committing when business work has not succeeded.

## 8. Distinguishing stop, pause, and crash

| Action | Consumer container | Partition assignment | Record processing capability |
|---|---|---|---|
| `pause()` | Keeps running and keeps polling | Typically retains assignment | Temporarily stops receiving records from paused partitions |
| `resume()` | Resumes normal operation | Retains assignment if no group changes occurred | Receives and processes records again |
| `stop()` | Stops container and closes consumer | Consumer leaves group, partitions are redistributed | Terminates per lifecycle and acknowledgment mode |
| Abrupt crash/kill | No controlled shutdown process | Kafka detects consumer departure after timeout or closed connection | Uncommitted records may be re-read; already-applied side effects may repeat |

If the goal is brief maintenance and avoiding a rebalance, `pause()` may be more appropriate. If deploying or shutting down an instance, use lifecycle shutdown so the container closes properly. Crashes are failure scenarios the system must still tolerate; do not treat graceful shutdown as the sole mechanism ensuring reliability.

## 9. Common misconceptions

1. **Calling `KafkaConsumer.close()` directly from another thread.** The consumer is owned by the Spring Kafka container; stop the container via the registry or lifecycle.
2. **Assuming `stop()` means all side effects are committed.** Committing depends on the acknowledgment mode, transactions, and when the listener finishes.
3. **Assuming uncommitted records are lost.** When a consumer leaves a group, uncommitted records can normally be re-read by a new consumer as long as the data remains within retention.
4. **Setting inner timeouts longer than platform timeouts.** The process may be killed before Spring finishes shutting down.
5. **Closing the database client before the listener container.** Listeners may still need that dependency to finish in-flight work.
6. **Using pause as shutdown.** Pause keeps the container in the group; stop terminates the container and releases assignments.
7. **Assuming graceful shutdown guarantees exactly-once.** Records can still be reprocessed; side effects need idempotency or appropriate transactions.

Closing a consumer safely is part of operational design for messaging flows. With Spring Kafka, let the listener container manage the consumer, choose an acknowledgment mode aligned with business logic, align timeouts across the container, Spring, and the deployment platform, and ensure listeners can tolerate reprocessing if shutdown cannot finish in time.
