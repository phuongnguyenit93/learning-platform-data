# Migrating from Legacy Configuration

A Spring Kafka application may have run stably for years with XML beans, hand-written Java configuration, legacy Kafka client properties, or superseded error-handling APIs. When upgrading Spring Boot, Spring Kafka, or the Kafka client, simply bumping the dependency version can cause the application to fail compilation, send/receive records with different behavior, or alter retry and offset commit behavior.

Safe migration starts by inventorying current configuration and behavior, then upgrading layer by layer in a controlled manner. You must maintain compatibility across producers, consumers, topics, event contracts, and consumer groups while multiple versions are deployed simultaneously. In particular, do not treat the application starting up cleanly as proof that data is still being processed correctly.

This lesson belongs to the **Upgrades and Compatibility** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to migrate legacy Spring Kafka configurations to modern ones, identify common API changes, and execute verifiable, rollback-capable migrations.

## Learning outcomes

After this lesson, you will be able to:

- Inventory legacy Spring Kafka configurations before upgrading.
- Select compatible versions of Spring Boot, Spring Kafka, Kafka client, and Java.
- Migrate XML or scattered Java configs to centralized configuration.
- Understand `KafkaTemplate.send()` API changes across Spring Kafka generations.
- Migrate legacy error handlers to `CommonErrorHandler` and `DefaultErrorHandler`.
- Audit retry, DLT, acknowledgment, and offset commit behavior after migration.
- Update serializers/deserializers, type headers, and trusted packages.
- Preserve transactions, idempotence, and isolation levels.
- Preserve consumer groups and committed offsets.
- Execute rolling deployments, canaries, rollbacks, and compatibility testing.

## 1. Migration is a behavioral change, not just a dependency bump

A Spring Kafka application consists of multiple dependent layers:

~~~text
Spring Boot
    |
    v
Spring Kafka
    |
    v
Apache Kafka client
    |
    v
Kafka broker / cluster
    |
    +---- topic / partition / consumer group
    |
    +---- event contract / serializer
    |
    +---- retry / DLT / transaction
~~~

Upgrading one layer can affect others. For example:

- Upgrading Spring Boot can pull in different Spring Framework, Spring Kafka, and Kafka client versions.
- Spring Kafka changing the `KafkaTemplate` future API can break callback compilation.
- A new error handler can alter how seeks, retries, and offset commits occur.
- `JsonDeserializer` may apply type headers or trusted packages differently from legacy settings.
- A newer Kafka client may have different defaults or validations for producer idempotence, timeouts, and consumer groups.
- A broker upgrade can affect the protocol, transaction coordinator, or group behavior.

Therefore, you must verify compile compatibility, runtime compatibility, and data compatibility.

## 2. Inventorying the current configuration

Before changing code, build an inventory of everything currently in use.

| Area | What to record |
|---|---|
| Dependencies | Spring Boot, Spring Kafka, kafka-clients, Java, and dependency management. |
| Producer | Bootstrap servers, serializers, acks, retries, idempotence, batching, transaction ID. |
| Consumer | Group ID, deserializers, auto commit, AckMode, concurrency, poll settings. |
| Listener | `@KafkaListener`, container factory, method signature, batch/record mode. |
| Error handling | ErrorHandler, CommonErrorHandler, retry policy, recoverer, and DLT. |
| Serialization | JSON type headers, mappings, trusted packages, schema registry. |
| Transactions | KafkaTransactionManager, transaction ID prefix, isolation level. |
| Topics | Partition count, replication factor, retention, min ISR, and DLT topology. |
| Security | SASL, TLS, JAAS, ACLs, and secret sources. |
| Observability | Logs, metrics, tracing, consumer lag, and alerts. |
| Tests | EmbeddedKafka/Testcontainers, group IDs, offset assumptions, and DLT assertions. |

For each setting, document its current value, where it is declared, which bean uses it, and expected behavior. The same property can appear in application YAML, Java beans, environment variables, and custom factories; determine the final effective value that reaches the Kafka client.

Do not start by deleting all old configuration. First determine which configuration is actually in effect and which is merely leftover.

## 3. Defining the version matrix before upgrading

Spring Boot manages many dependencies through dependency management. Spring Kafka and the Kafka client must be chosen according to the compatibility matrix of your target Boot/Spring Kafka release.

Before upgrading, verify:

- Minimum Java version required by target Spring Boot and Spring Kafka.
- Spring Kafka version managed by Spring Boot.
- Kafka client version selected by dependency management.
- Broker version and protocol compatibility.
- Compatibility of serializer, schema registry, and test container libraries.
- Compatibility of build plugins, test frameworks, and observability exporters.

Do not arbitrarily override `spring-kafka` or `kafka-clients` versions just to use a new API. If an override is needed, document the reason, check release notes, and test against the corresponding real broker.

For a Spring Boot 2 to 3 migration, also account for the new Java baseline and Jakarta ecosystem changes in the application. This is a broader platform migration than Kafka alone; avoid bundling too many unrelated changes into a single deployment without adequate test coverage.

## 4. Using dependency management instead of scattered version declarations

Maven example with Spring Boot parent or BOM:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${spring-boot.version}</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.kafka</groupId>
        <artifactId>spring-kafka</artifactId>
    </dependency>
</dependencies>
~~~

With Spring Boot, the commonly used dependency is `org.springframework.kafka:spring-kafka`; Spring Boot dependency management manages its version when using the corresponding parent/BOM. Verify the artifact and version in your project version's dependency catalog.

If not using the parent, import the Spring Boot dependency BOM inside `dependencyManagement`. Avoid declaring mismatched versions for Spring Kafka and Kafka client without explicit compatibility verification.

After upgrading dependencies, inspect the dependency tree to detect multiple versions of Kafka client or Spring Kafka on the classpath. A classpath with version conflicts can compile cleanly yet fail at runtime with `NoSuchMethodError`, `ClassNotFoundException`, or linkage errors.

## 5. Migrating XML configuration to Java configuration or Spring Boot properties

Legacy applications may declare producer factories, consumer factories, `KafkaTemplate`, and listener container factories in XML. Modern applications can use Spring Boot auto-configuration combined with application YAML.

Basic producer/consumer configuration example:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      acks: all
    consumer:
      group-id: orders-fulfillment
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.acme.orders.contract
~~~

This is an illustrative configuration. Properties must be checked against your target Spring Boot version and actual serializers.

When using Boot auto-configuration, you do not need to manually define every bean if defaults meet your requirements. If you declare a custom `ProducerFactory`, `ConsumerFactory`, or `KafkaTemplate`, verify whether that bean receives all Boot properties; custom beans do not automatically inherit settings you do not pass to them.

## 6. When should you keep custom ProducerFactory and ConsumerFactory beans?

Custom factories remain necessary when an application connects to multiple Kafka clusters, uses different principals, different serializers, or consumer groups with distinct policies.

Example creating a `ConsumerFactory` from properties:

~~~java
@Bean
ConsumerFactory<String, OrderCreatedEvent> orderConsumerFactory(
        KafkaProperties kafkaProperties,
        SslBundles sslBundles) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildConsumerProperties(sslBundles));

    properties.put(
            ConsumerConfig.GROUP_ID_CONFIG,
            "orders-fulfillment"
    );

    return new DefaultKafkaConsumerFactory<>(properties);
}
~~~

The `KafkaProperties.buildConsumerProperties()` signature may accept additional parameters or change across Spring Boot versions. During migration, use the exact signature from your target version rather than copying examples from a different release.

If multiple factories share bootstrap servers but differ in group ID or deserializer, give beans clear names and bind the right `containerFactory` on each listener. Avoid creating duplicate factories with undocumented differences.

## 7. Migrating KafkaTemplate.send(): ListenableFuture to CompletableFuture

A notable change in Spring Kafka 3.0 is that `KafkaTemplate.send()` switched from `ListenableFuture` to `CompletableFuture`.

Legacy code may use Spring callbacks:

~~~java
ListenableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send(topic, event.orderId(), event);

future.addCallback(
        result -> log.info("Sent"),
        error -> log.error("Send failed", error)
);
~~~

In Spring Kafka 3.x, use `CompletableFuture`:

~~~java
CompletableFuture<SendResult<String, OrderCreatedEvent>> future =
        kafkaTemplate.send(topic, event.orderId(), event);

future.whenComplete((result, error) -> {
    if (error == null) {
        log.info(
                "Sent topic={}, partition={}, offset={}",
                result.getRecordMetadata().topic(),
                result.getRecordMetadata().partition(),
                result.getRecordMetadata().offset()
        );
    } else {
        log.error("Send failed", error);
    }
});
~~~

Other options include `thenApply`, `thenCompose`, `exceptionally`, or `handle`. Always handle exceptions from the future; if you ignore the future, publish failures may go unobserved in the right place.

Do not block threads with `get()` on the request path unless necessary. If business logic requires broker confirmation before returning a response, use a bounded timeout and handle timeouts/failures explicitly. Callbacks should remain short and avoid heavy blocking work.

## 8. Migrating legacy error handlers to CommonErrorHandler

Older Spring Kafka versions may use `ErrorHandler`, `BatchErrorHandler`, or `SeekToCurrentErrorHandler`. In newer versions, the `CommonErrorHandler` model unifies error handling for record and batch listeners; `DefaultErrorHandler` is the standard implementation.

Configuration example:

~~~java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    FixedBackOff backOff = new FixedBackOff(1_000L, 2L);

    return new DefaultErrorHandler(recoverer, backOff);
}
~~~

Attach to the factory:

~~~java
factory.setCommonErrorHandler(commonErrorHandler);
~~~

Verify constructors, packages, and APIs against the target version. If the legacy project customized seek/retry behavior, do not replace it with a default `DefaultErrorHandler` without reproducing the desired semantics.

Verify:
- Which exceptions are retried and which are not retried.
- Retry count and backoff.
- When partitions are seeked and records redelivered.
- When recovery to a DLT occurs.
- How offsets are committed upon recovery.
- Whether batch listeners have different semantics from record listeners.
- Whether the DLT-publishing recoverer has the right serializer and destination.

## 9. Migrating retry and DLT

Retry can be implemented as blocking retry in an error handler or as non-blocking retry topics. These are two different models and cannot be swapped simply by changing an annotation.

With blocking retry, the consumer may pause partition progress during backoff/retry. With retry topics, records are routed through scheduled retry topics, which can alter relative ordering between events.

During migration, record:

- Number of attempts and backoff.
- Exception classification.
- Retry topic and DLT names.
- Partition count/replication/retention of retry topics.
- DLT headers and original metadata.
- Replay procedure and ownership of failed records.
- Ordering guarantees that the business logic relies upon.

If migrating to `@RetryableTopic`, verify your Spring Kafka version supports the annotation and appropriate configuration. Do not accidentally enable both retry topics and blocking retries for the same error, as total attempts and processing time can diverge drastically from expectations.

## 10. Reviewing AckMode and offset commits

Migration can inadvertently change AckMode, `enable.auto.commit`, or transaction semantics. This can lead to duplicates or lost records at the application level.

Common AckModes:

| AckMode | General meaning |
|---|---|
| RECORD | Commits after each record is processed successfully. |
| BATCH | Commits after processing all records in a poll batch. |
| TIME / COUNT | Commits based on elapsed time or record count, depending on configuration. |
| MANUAL | Listener actively acknowledges; the container manages commits under manual semantics. |
| MANUAL_IMMEDIATE | Acknowledge on the consumer thread can commit immediately. |

Do not assume defaults across versions or custom factories are identical. Inspect the effective configuration of each container.

During migration:
1. Keep the same group ID if you want to resume from current committed offsets.
2. Check `enable.auto.commit` and AckMode.
3. Check whether the error handler seeks or commits recovered offsets.
4. Verify manual acknowledgment is invoked on the right thread.
5. Verify transaction commits and offset commits preserve prior semantics.
6. Test crashing after side effects but before commit to observe redelivery.

`auto.offset.reset` only applies when the group has no valid committed offset. Changing this setting does not reset offsets for an active group.

## 11. Migrating serializers and deserializers

Legacy JSON configurations may rely on FQCNs in type headers, overly broad trusted packages, or unclear default target types. When upgrading, inspect the actual wire format.

Example using stable type mappings:

~~~yaml
spring:
  kafka:
    producer:
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        spring.json.type.mapping: order-created:com.acme.orders.OrderCreated
    consumer:
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.type.mapping: order-created:com.acme.fulfillment.contract.OrderCreated
        spring.json.trusted.packages: com.acme.fulfillment.contract
~~~

Producer and consumer use classes in different packages while sharing the same token. This reduces coupling to FQCNs; however, the JSON payload must still remain compatible.

If you need to handle deserialization exceptions via an error handler, consider `ErrorHandlingDeserializer` wrapping the appropriate delegate deserializer. Verify type headers, default types, trusted packages, header removal, and schema compatibility.

Do not change serializers solely to make code compile. Changing serializers can alter the bytes written to Kafka and affect every consumer reading the topic.

## 12. Migrating listener methods and container factories

Legacy listeners may use `@KafkaListener` with simple method signatures or customized container factories.

Example:

~~~java
@KafkaListener(
        id = "ordersListener",
        topics = "${app.kafka.topics.orders}",
        groupId = "${spring.kafka.consumer.group-id}",
        containerFactory = "ordersKafkaListenerContainerFactory"
)
public void consume(ConsumerRecord<String, OrderCreatedEvent> record) {
    orderService.handle(record.value());
}
~~~

Audit the legacy method signature:
- Plain payload object or `ConsumerRecord`.
- Does it accept `Acknowledgment`?
- Record listener or batch listener.
- Does it use `Message<?>` and a message converter?
- Does it need keys, headers, partition, or offset?
- Are there custom filters/interceptors?
- Does the selected factory have the right deserializer, error handler, and AckMode?

If switching from a payload parameter to `ConsumerRecord` or vice versa, check message conversion and the listener adapter. Do not assume changing only the parameter type is equivalent.

## 13. Migrating listener container factories

Factories typically centralize shared policies for listeners. When upgrading, compare every property rather than creating a new factory from a default template.

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>
ordersKafkaListenerContainerFactory(
        ConsumerFactory<String, OrderCreatedEvent> consumerFactory,
        CommonErrorHandler commonErrorHandler) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreatedEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setCommonErrorHandler(commonErrorHandler);
    factory.setConcurrency(3);

    factory.getContainerProperties()
            .setAckMode(ContainerProperties.AckMode.RECORD);

    return factory;
}
~~~

Review concurrency against partition counts and downstream capacity. Check poll timeouts, idle events, record filters, record interceptors, observation, and shutdown behavior if the application relies on those features.

If the legacy factory had custom properties applied after bean creation, ensure the migration still applies them before the container starts.

## 14. Migrating transactions and producer idempotence

If the application uses Kafka transactions, preserve the producer transactional ID prefix, transaction manager, and listener container transaction integration.

Example Boot configuration declaration:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: ${KAFKA_TRANSACTION_ID_PREFIX}
    consumer:
      properties:
        isolation.level: read_committed
~~~

Property names and auto-configuration depend on the Spring Boot version. With a custom `ProducerFactory`, verify the transaction ID prefix is set on the factory and that prefixes are unique across concurrently running application instances.

During migration:
- Verify transactional IDs do not collide unintentionally.
- Verify `KafkaTransactionManager` and `KafkaTemplate` use compatible `ProducerFactory` instances.
- Check transaction timeouts against listener processing duration.
- Keep consumer `isolation.level=read_committed` if aborted transactions must be hidden.
- Verify output records and consumed offsets are committed in the same Kafka transaction when using EOS.
- Remember that Kafka transactions do not automatically roll back database or HTTP side effects.

Do not enable transactions in new code without verifying ACLs for transactional IDs and recovery behavior.

## 15. Migrating security properties

Legacy applications may declare SASL/TLS directly in Java properties or separate client files. You can migrate them to Spring Boot configuration for centralized management:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
      ssl.truststore.location: ${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

If producer, consumer, and AdminClient use different principals, declare separate properties for each client. Never move real secrets into committed YAML files.

After migration, verify:
- Actual effective principals.
- Topic and group ACLs.
- TLS trust chains and hostname verification.
- Whether secret rotation applies to new clients or running clients.
- Logs do not expose JAAS strings, passwords, or tokens.
- Negative tests still reject unauthorized operations.

## 16. Maintaining compatibility with consumer groups and legacy data

Consumer groups hold persistent state in Kafka. Changing a group ID creates a new group, usually causing the application to start according to `auto.offset.reset` if no committed offsets exist.

During migration, do not change the group ID merely to distinguish releases if your goal is to continue reading from the current position. If you must run a canary with a new group, understand that the canary may re-read data and cause duplicate side effects.

Before rollout:
- Record group IDs and committed offsets per partition.
- Verify topic retention is sufficient for the migration window.
- Ensure the new consumer can read older existing records.
- Keep event schemas compatible during the overlap period.
- Determine whether pausing, draining, or transferring ownership is needed.
- Do not reset offsets to "clean up" a migration without a replay plan.

An offset is the next position to read; when checking the last processed record, understand commit semantics and the redelivery window.

## 17. Compatibility between producer and consumer

Producers and consumers can be deployed independently. During a rolling deployment, different versions may run simultaneously and exchange records.

Compatibility matrix to evaluate:

| Producer | Consumer | Question to verify |
|---|---|---|
| Old | Old | Does the current baseline work properly? |
| Old | New | Can the new consumer read old payloads? |
| New | Old | Can the old consumer read new payloads? |
| New | New | Are the new contract and behavior correct? |

Changes prone to breaking compatibility:
- Changing field types or formats.
- Adding enum values unknown to old consumers.
- Changing type headers or tokens.
- Changing serializers.
- Changing keys or partitioning strategies.
- Changing topics, group IDs, or header semantics.
- Changing retry/DLT routing.
- Changing default values or null handling.

For each change, determine backward compatibility (new consumer reads old data), forward compatibility (old consumer reads new data), and full compatibility per your event contract policy.

## 18. Rolling migration strategy

A commonly used sequence:

1. Inventory current versions, configurations, and behaviors.
2. Upgrade consumer code first if the new consumer needs to support new payloads.
3. Deploy the new consumer able to read both old and new payloads.
4. Verify group membership, partition assignments, offsets, and lag.
5. Deploy the new producer without emitting incompatible changes yet.
6. Enable emitting new payloads after compatible consumers are ready.
7. Monitor send errors, deserialization errors, retries, DLT, and business state.
8. Only drop support for old payloads after the overlap and retention windows have been accounted for.

Even if a migration only changes internal APIs without changing wire formats, still run a canary to catch runtime behavioral changes such as retries, acknowledgments, and transactions.

Do not run two consumer groups both executing production side effects just to compare versions unless you have proper shadow-processing isolation or idempotency.

## 19. Canaries and feature flags for behavioral changes

Canary deployments or feature flags can limit the blast radius of a change, for example:

- Only one instance uses the new error handler.
- Only one producer route emits the new event contract.
- A shadow consumer group reads data without producing side effects.
- Enable the new serializer on a test topic first.
- Increase concurrency incrementally.

Feature flags do not solve compatibility on their own. If two versions write to the same topic, they must still conform to the same wire contract, or consumers must support both.

Canaries need separate metrics by version/listener while avoiding excessive label cardinality. Define stop conditions upfront: error rate, p99 latency, lag, DLT rate, or business invariants.

## 20. Rollback plan

Rollback is not merely redeploying the old binary. If the new version has written new payloads, created new topics, altered offsets, or changed side effects, old code may fail to read the new state.

Before migration, document:
- Old artifact/version ready to redeploy.
- Old configuration and secret references remain valid.
- Whether the new producer emits a wire format older consumers understand.
- Whether consumer groups/offsets remain intact.
- Whether DLT/retry topics changed schemas or naming.
- Whether database migrations are backward-compatible.
- Whether producers must stop or consumers must pause during rollback.
- How to handle records published during the migration window.

Rollback is safest when wire contracts and data formats remain backward-compatible. If incompatible data has already been emitted, you may need a forward fix or compatibility adapter instead of simply reverting to the old binary.

## 21. Pre- and post-migration testing

A migration test suite should cover:

| Test category | What to verify |
|---|---|
| Build/compile | Legacy APIs replaced and no dependency conflicts. |
| Producer | Send futures, acks, error callbacks, and serialization. |
| Consumer | Deserialization, listener invocation, and group ID. |
| Offsets | AckMode, manual ack, redelivery, and committed offsets. |
| Error handler | Retry counts, backoff, recoverer, and DLT. |
| Transactions | Commit, abort, fencing, and read_committed. |
| Security | SASL/TLS, principals, and ACLs. |
| Compatibility | Old/new producer with old/new consumer. |
| Operations | Metrics, logs, lag, shutdown, and rebalances. |
| Failure | Crash between side effect and offset commit, broker unavailable, dependency timeout. |

Use EmbeddedKafka for fast integration tests and Testcontainers or cluster integration for behavior depending on broker/security/version. Configuration unit tests do not replace end-to-end tests.

When testing offsets, use dedicated group IDs per test or manage offsets explicitly. Do not let tests depend on leftover data from previous runs.

## 22. Phased migration checklist

**Before upgrading**

- [ ] Record Java, Spring Boot, Spring Kafka, and Kafka client versions.
- [ ] Save the dependency tree and effective configuration.
- [ ] Record group IDs, topics, partitions, and committed offsets.
- [ ] Record AckMode, auto commit, retry, DLT, and transaction behavior.
- [ ] Save baseline throughput, latency, lag, and error rates.
- [ ] Verify wire contracts and serializers/deserializers.
- [ ] Prepare rollback artifacts and configurations.

**During upgrade**

- [ ] Use compatible dependency management.
- [ ] Fix compile-time APIs such as the `KafkaTemplate` future.
- [ ] Migrate error handlers and retries preserving intended semantics.
- [ ] Keep serializers, type mappings, and header contracts compatible.
- [ ] Preserve group IDs/offsets unless there is a data migration plan.
- [ ] Verify SASL/TLS/ACLs and transactions.
- [ ] Deploy canary and observe metrics.

**After upgrade**

- [ ] Producer sends succeed.
- [ ] Consumer assignments are stable.
- [ ] Offsets advance properly according to AckMode.
- [ ] Retry/DLT operates according to policy.
- [ ] Business state has no missing items or unexpected duplicates.
- [ ] Throughput, p95/p99, and lag are within thresholds.
- [ ] Logs/metrics are intact and do not expose secrets.
- [ ] Runbooks and configuration documentation are updated.

## 23. Common migration mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Only bumping dependency versions | Runtime behavior can change unchecked | Build a version matrix and test each layer. |
| Overriding Kafka client arbitrarily | `NoSuchMethodError` or protocol mismatch | Use Boot dependency management and inspect the dependency tree. |
| Keeping `ListenableFuture` callbacks on new APIs | Compile failure | Migrate to `CompletableFuture` APIs. |
| Changing ErrorHandler without testing seek/commit | Duplicate or skipped records | Verify retry, recoverer, and offset semantics. |
| Changing group ID during rollout | Consumer starts from a different offset | Keep the group ID or plan an explicit replay. |
| Changing serializer and schema at the same time | Old consumers cannot read data | Split the changes and verify wire compatibility. |
| Widening trusted packages overly broadly | Increases risk of deserializing unexpected classes | Allowlist only required contract packages. |
| Enabling transactions with duplicate prefixes | Producer fencing | Generate unique prefixes per instance/lifecycle. |
| Only testing application startup | Misses errors that occur when sending/consuming | Send real records and verify side effects/offsets. |
| Rolling back binary after emitting new schema | Old code cannot read new records | Design backward-compatible rollouts or forward fixes. |

## 24. Comprehensive exercise: migrating Order Service

Suppose Order Service currently uses legacy Spring Kafka with XML config, `ListenableFuture` callbacks, and `SeekToCurrentErrorHandler`. The goal is to migrate to Spring Boot configuration, `CompletableFuture`, and `CommonErrorHandler`.

Requirements:

1. Record Java, Boot, Spring Kafka, and Kafka client versions.
2. Inventory producers, consumers, listener factories, serializers, transactions, and security.
3. Choose a version matrix managed by the Boot BOM.
4. Move bootstrap, serializers/deserializers, and group ID into controlled configuration.
5. Migrate necessary custom beans to Java config and remove duplicate beans.
6. Migrate `KafkaTemplate` callbacks to `CompletableFuture`.
7. Migrate the error handler to `CommonErrorHandler`/`DefaultErrorHandler` matching the old retry semantics.
8. Verify DLT destination, headers, and recoverer.
9. Preserve AckMode, group ID, and committed offsets.
10. Verify JSON type mapping and trusted packages.
11. Verify transaction ID prefix, transaction manager, and `read_committed`.
12. Run tests for producer/consumer, retry, DLT, offsets, transactions, and ACLs.
13. Deploy a consumer canary before changing the producer wire format.
14. Monitor throughput, p99 latency, consumer lag, and error rate.
15. Rehearse rollback with records emitted during the migration window.
16. Document the final configuration and operational runbook.

The exercise is complete when the new application processes old records, producers/consumers remain compatible during the overlap window, offsets are not reset unexpectedly, and retry/transaction semantics remain accurate.

## 25. Learning order and completion criteria

| Stage | Core content | Self-check criteria |
|---|---|---|
| 1. Inventory | Dependencies and current config | Can identify every active bean/property. |
| 2. Version matrix | Boot, Spring Kafka, Kafka client, Java | Selected a compatible version set. |
| 3. Configuration | XML/Java config and Boot properties | Removed duplicate config without losing behavior. |
| 4. Producer API | `ListenableFuture` and `CompletableFuture` | Migrated callbacks and send error handling. |
| 5. Error handling | `ErrorHandler` and `CommonErrorHandler` | Preserved retry, seek, recovery, and DLT. |
| 6. Serialization | Type headers, mappings, schemas | Can read both old and new payloads. |
| 7. Offsets | AckMode, group ID, and committed offsets | No unintended resets or bad commits. |
| 8. Transactions | Transaction manager, fencing, isolation | Verified commit/abort and `read_committed`. |
| 9. Deployment | Canary, rolling upgrade, and rollback | Upgraded versions without breaking contracts. |
| 10. Verification | Tests, metrics, business integrity | Proved the new pipeline is compatible. |

This lesson is complete when you can plan a migration from legacy Spring Kafka configurations, identify API/configuration changes, preserve critical offset/retry/transaction semantics, and execute a rolling upgrade with canaries, rollback, and test evidence.

A migration succeeds when producers and consumers continue exchanging events accurately, offsets advance properly, retry/DLT and transactions honor their committed semantics, and the system can roll back or forward-fix without sacrificing data integrity.

