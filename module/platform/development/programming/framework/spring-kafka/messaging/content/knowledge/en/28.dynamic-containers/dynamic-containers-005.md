# Stopping and Removing Dynamic Containers

Spring Kafka allows creating listener containers while an application is running—for example, giving each tenant or topic its own consumer. When consumption is no longer needed, the application must stop the container following its proper lifecycle and release the managed reference. This operation only affects the consumer container within the application; it does not delete the Kafka topic, records, or committed offsets of the consumer group.

Three operations should be distinguished: `pause()` temporarily halts receiving records while keeping the container active; `stop()` stops the consumer and ends its running lifecycle; `destroy()` releases resources of an application-owned container. If the container is registered in `KafkaListenerEndpointRegistry`, there is also an `unregisterListenerContainer()` step to remove the container from the registry.

## 1. Distinguishing pause, stop, destroy, and unregister

| Operation | Purpose | Can It Resume Running? |
| --- | --- | --- |
| `pause()` | Temporarily pauses consuming assigned partitions; container keeps polling and can resume. | Yes, by calling `resume()`. |
| `stop()` | Stops the listener container, shuts down running consumers, and leaves the consumer group. | Can call `start()` again on a still-managed container. |
| `destroy()` | Releases resources of the container instance when no longer needed. | Should not restart a destroyed instance; create a new instance if needed. |
| `unregisterListenerContainer(id)` | Removes the container reference from `KafkaListenerEndpointRegistry`. | A new container can be registered with that ID after the old one is stopped and removed. |

`pause()` fits backpressure or brief maintenance. `stop()` fits when a tenant stops using the service or consumer configuration must be replaced. `destroy()` is for containers whose resources are managed by the application. `unregister` only modifies the registry and does not automatically stop the consumer.

Stopping a container does not delete Kafka data. The group's committed offsets remain stored on the broker; if a new container is created with the same `group.id`, the consumer resumes from the committed offsets. If resetting offsets or deleting topics is required, that is a separate Kafka administrative operation and must follow a clear policy.

## 2. Creating Dynamic Containers with a Container Factory

When you want to manage a listener yourself, you can use `ConcurrentKafkaListenerContainerFactory.createContainer(topic)` to create a container directly. The application is responsible for keeping the reference, setting the group ID, attaching the listener, starting, stopping, and destroying that instance.

```java
public ConcurrentMessageListenerContainer<String, String> createContainer(
        ConcurrentKafkaListenerContainerFactory<String, String> factory,
        String topic,
        String groupId,
        String containerName) {

    ConcurrentMessageListenerContainer<String, String> container =
        factory.createContainer(topic);
    container.getContainerProperties().setGroupId(groupId);
    container.getContainerProperties().setMessageListener(
        (MessageListener<String, String>) record ->
            orderService.process(record.value()));
    container.setBeanName(containerName);
    container.start();
    return container;
}
```

Containers created from a factory use the `ConsumerFactory` and shared factory settings. Set `groupId` before starting. When using `ConcurrentMessageListenerContainer`, concurrency may create multiple child consumer containers; manage the parent container returned by the factory to control the entire group.

In a real application, store containers under a stable business ID, such as a normalized tenant ID. Do not generate IDs from unvalidated input or allow two requests to create the same ID concurrently. Use a `ConcurrentHashMap` or a lifecycle management service to ensure each ID has at most one active instance.

## 3. Stopping Self-Created Containers and Releasing Resources

Do not remove a container from the map immediately after calling `stop()`. Stopping can happen asynchronously; the `stop(Runnable)` callback is invoked when the container finishes stopping. Only inside or after the callback should you destroy the instance and remove the managed reference.

```java
public void stopAndRemove(String id) {
    ConcurrentMessageListenerContainer<String, String> container =
        containers.get(id);
    if (container == null) {
        return;
    }

    container.stop(() -> {
        container.destroy();
        containers.remove(id, container);
    });
}
```

Use `remove(id, container)` to avoid accidentally removing a newer instance if the same ID was replaced while the callback completed. In a full service, use locks or manage states (`STARTING`, `RUNNING`, `STOPPING`, `STOPPED`) so a new start command cannot race with an older stop callback.

When stopping, the container finishes or terminates processing according to its shutdown timeout and lifecycle, then closes the consumer. Configure the shutdown timeout appropriately for the listener's maximum processing duration. Do not close `KafkaConsumer` directly inside the listener or from a management thread; the consumer is owned by the container and must be closed through the container lifecycle.

## 4. Stopping and Unregistering Containers Managed by @KafkaListener

Containers created from `@KafkaListener` are not ordinary beans in the application context. Spring Kafka registers and manages them through `KafkaListenerEndpointRegistry`. Retrieve the container using the annotation's ID and invoke lifecycle methods on that specific container.

```java
@KafkaListener(
    id = "tenant-orders-42",
    topics = "orders.tenant-42",
    groupId = "orders-tenant-42",
    autoStartup = "false")
public void listen(OrderEvent event) {
    orderService.process(event);
}
```

You can start or stop a listener by ID:

```java
MessageListenerContainer container =
    registry.getListenerContainer("tenant-orders-42");

if (container != null) {
    container.start();
}
```

Since Spring Kafka 2.8.9, `KafkaListenerEndpointRegistry` provides `unregisterListenerContainer(id)`. The sequence to stop and remove a container is:

```java
public void stopAndUnregister(String id) {
    MessageListenerContainer container = registry.getListenerContainer(id);
    if (container == null) {
        return;
    }

    container.stop(() -> registry.unregisterListenerContainer(id));
}
```

`unregisterListenerContainer` only removes the container from the registry; it does not call `stop()` or other lifecycle/disposable methods. Therefore, you must stop the container before unregistering. After removal, the ID can be reused for a new endpoint/container. On Spring Kafka versions earlier than 2.8.9, this unregister API does not exist; you can stop the container, though the registry retains the registration until the application context ends.

Containers declared as beans in the application context are not managed by `KafkaListenerEndpointRegistry`. Retrieve them from the context and let Spring manage their lifecycle or invoke lifecycle methods as defined for that bean; do not look them up via `registry.getListenerContainer(id)`.

## 5. Re-registering a Container with the Same ID

When using dynamic endpoints or prototype beans with `@KafkaListener`, the listener ID must be unique in the registry. After the old container has stopped and been unregistered, that ID can be reused. Do not register a new container immediately upon issuing a stop command because the old consumer may still be processing records and may not have left the group yet.

With prototype beans, each instance can receive a different ID and topic. When creating an instance after the application context has refreshed, the container may auto-start per the registry's lifecycle rules; control `autoStartup` and `alwaysStartAfterRefresh` according to your Spring Kafka version if startup needs to be deferred.

## 6. What Happens to the Consumer Group and Offsets?

When a container stops, the consumer closes and leaves the group. Kafka may perform a rebalance to redistribute its partitions to remaining consumers. Committed offsets remain on the broker. A new container using the same `group.id` continues from the committed offsets; if using a new group ID, Kafka applies `auto.offset.reset` when the group has no committed offsets yet.

Records in-flight at stop time must be considered in light of the acknowledgment mode. If a record finished processing and its offset was committed, it will not be redelivered to the group. If the process stops before committing, the record may be redelivered to another consumer or when the container restarts. Consequently, listeners still need to be idempotent, and stopping should not be treated as a guarantee that all external side effects have finished.

Do not call `destroy()` expecting to delete the consumer group or committed offsets. If the business requirement is to delete a group or reset offsets, use the Kafka Admin API or separate administrative tools after confirming no active consumers remain in the group.

## 7. Avoiding Race Conditions During Start and Stop

Dynamic containers are often managed by APIs or jobs that can receive concurrent commands. A start request may arrive while a stop is in progress; two stop requests may read the same reference. Without a state machine, the application can easily create two containers for the same tenant or remove a reference before the old consumer closes.

A lifecycle service should enforce these rules:

- Create a container only when the ID has no existing container in `STARTING`, `RUNNING`, or `STOPPING` state.
- Transition to `STOPPING` before calling `stop()` to reject duplicate start commands.
- Mark `STOPPED` and remove from the map only after the stop callback completes.
- If restarting is needed, create a new instance after the old instance has stopped and been destroyed.
- Handle callback failures or timeouts with an observable error state and operational retry mechanism.

If multiple application instances manage a tenant, an in-memory map is insufficient to guarantee cluster-wide uniqueness. Distributed coordination or explicit tenant ownership assignment is needed to prevent two instances from creating consumers contrary to policy.

## 8. When to Pause Instead of Stop?

Use `pause()` when you want to temporarily halt record delivery while keeping the consumer and its assignments, such as when a downstream dependency is overloaded or undergoing brief maintenance. The container continues polling to maintain the consumer group; once conditions recover, call `resume()`.

Use `stop()` when you want to release the consumer, change configuration, or end the container lifecycle. On stop, the consumer leaves the group and can cause a rebalance. If the goal is simply rate throttling or a temporary pause in processing, pausing generally disrupts assignments less.

## 9. Testing Dynamic Container Lifecycle

An integration test should create a container from a factory, send a record to the topic, and verify the listener receives it. Then call `stop(Runnable)` and wait for the callback; verify `isRunning()` is `false`, the consumer receives no new records, and the reference is removed from the map.

For registry-managed containers, test looking up by the right ID, stopping, and then unregistering; then verify `getListenerContainer(id)` returns `null` and the ID can be re-registered if supported by the version. Also test two concurrent stop commands, starting during a stop, consumer initialization failures, shutting down while the listener is processing, and restarting with the same group ID to verify offsets resume properly.

Use Embedded Kafka or Testcontainers to observe consumer groups, rebalances, and committed offsets. Do not merely check the `isRunning` flag; verify the consumer has actually stopped polling and no longer processes records after the lifecycle callback completes.

## 10. Operations Checklist

- Assign unique IDs and clearly track whether a container is managed by a factory or the registry.
- Set `group.id`, listener, concurrency, and required properties before calling `start()`.
- Use `pause/resume` for temporary halts; use `stop` to end the lifecycle.
- Wait for the `stop(Runnable)` callback before destroying, unregistering, or removing references.
- Call `unregisterListenerContainer` only on Spring Kafka 2.8.9 or later, and remember that unregistering does not stop the container.
- Monitor states, running container counts, consumer groups, rebalances, and shutdown timeouts.
- Limit dynamic container counts to avoid creating excessive consumer threads, sockets, and broker connections.

Stopping and removing dynamic containers is a lifecycle workflow: stop the consumer, wait for shutdown to finish, release application-owned resources, and unregister from the management store. When `pause`, `stop`, `destroy`, and `unregister` are properly distinguished, the application can create and reclaim consumers on demand without confusing this with deleting Kafka topics or offsets.

## References

- [Dynamically Creating Containers - Spring Kafka](https://docs.spring.io/spring-kafka/reference/kafka/dynamic-containers.html)
- [@KafkaListener Lifecycle Management - Spring Kafka](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/kafkalistener-lifecycle.html)
