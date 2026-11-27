# Declaring State Stores and materializedAs

## Objectives

Kafka Streams can aggregate data, retain state by key, and update results as new records arrive. This state is stored in a **state store**. For instance, a topology can maintain total order counts per customer, current balances per account, or event counts within each time window.

In the Spring Cloud Stream Kafka Streams binder, state stores are typically created from Kafka Streams DSL operations such as `aggregate`, `count`, and `reduce`. The **Materialized.as(...)** API names and describes how an operation's result is materialized. For certain bindings with a `KTable` input type, the binder's **materializedAs** property lets you name the state store created by the binder for that binding.

Store names are part of the operational contract: applications can use the name to execute interactive queries, monitor state restoration, and identify stores in the topology. This lesson explains how to declare stores, pick store types and Serdes, configure `materializedAs`, query state, and manage changelogs/recovery.

After this lesson, you will be able to:

- Explain what a state store is and its role in Kafka Streams.
- Distinguish `KStream`, `KTable`, and state stores.
- Create stores with `Materialized.as(...)` in aggregation operations.
- Configure `materializedAs` for a `KTable` binding when the binder materializes incoming data.
- Choose `KeyValueStore`, `WindowStore`, or `SessionStore` according to access patterns.
- Configure key/value Serdes and stable store names.
- Query stores using `KafkaStreamsInteractiveQueryService`.
- Understand changelogs, state restoration, caching, and the boundaries of local state.
- Test stores across startup, updates, and restoration.

## 1. What Is a State Store?

A state store is where Kafka Streams stores the state a topology needs to process subsequent records. Unlike a stateless transformation that handles each record in isolation, a stateful operation must remember prior data.

Examples:

- Counting orders by `customerId`.
- Calculating total revenue per store.
- Storing the latest status of each account.
- Maintaining metrics across 5-minute windows.
- Joining an event stream with a reference table.

Suppose a stream receives these events:

| customerId | orderId | amount |
|---|---|---:|
| C-01 | O-100 | 120 |
| C-02 | O-101 | 80 |
| C-01 | O-102 | 50 |
| C-01 | O-103 | 30 |

Counting by `customerId` requires retaining the current count. After four records, the state store may contain:

| Key | Count |
|---|---:|
| C-01 | 3 |
| C-02 | 1 |

When the next record for `C-01` arrives, Kafka Streams reads the old state, updates the value, and writes the new state. The application does not have to load the entire topic history into memory and recompute from scratch each time.

A state store is typically bound to a Kafka Streams task/partition. Data for a given key is processed by the task owning that partition, so state is partitioned alongside the topology. A store may have multiple local shards across different instances; never assume a single instance holds data for every key.

## 2. Distinguishing KStream, KTable, and State Stores

These three concepts are related, not synonymous:

| Component | Meaning | How to Think About It |
|---|---|---|
| KStream | Stream of event records | Each record is an independent event |
| KTable | Table updated by key | Each record updates the current value of a key |
| State store | Local state storage mechanism of the topology | Stores data for aggregations, joins, or queries |

KStream fits event histories: an order being created, paid, and shipped are distinct records. KTable represents the latest state by key: the current status of order `O-100` can transition from `CREATED` to `PAID`.

A KTable is typically backed by a state store. However, not every state store comes from a KTable input binding; aggregation operations in the DSL also materialize state stores.

Example of a KStream aggregated into a KTable:

    KTable<String, Long> orderCount = orders
            .groupByKey(Grouped.with(Serdes.String(), orderEventSerde))
            .count();

`count` needs state to remember counts per key. Kafka Streams materializes the result into a state store and exposes the updated results as a KTable.

## 3. Materialized.as(...) Names a State Store

In the Kafka Streams DSL, `Materialized` describes how a result is materialized. The `as(...)` method assigns the store name. That name is used inside the topology and can be used to query the store if the store type supports queries.

Example counting orders by `customerId`:

    KTable<String, Long> orderCountByCustomer = orders
            .groupByKey(Grouped.with(
                    Serdes.String(),
                    orderEventSerde
            ))
            .count(
                    Materialized
                            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                                    "orders-count-by-customer"
                            )
                            .withKeySerde(Serdes.String())
                            .withValueSerde(Serdes.Long())
            );

In this example:

- The key is `customerId` of type `String`.
- The state store value is the order count of type `Long`.
- The store name is `orders-count-by-customer`.
- Key Serde and value Serde define how data is stored and restored.
- The `KTable` reflects the current count after every update.

Store names should be stable and carry business meaning. Avoid generating random names based on timestamps or instance IDs, as doing so complicates state restoration, interactive queries, and operations.

### Materialized.as(...) Is Not an Output Topic Name

A store name and a Kafka topic name are two separate things. A state store may have a changelog topic managed by Kafka Streams for state recovery. The changelog topic does not necessarily share the exact store name and is not the business output topic that downstream consumers subscribe to.

If a topology both materializes state and emits results to a topic, configure a separate output binding destination. Never use the store name as an output binding's destination.

## 4. Configuring Serdes for a State Store

A state store must know how to serialize keys and values. If Serdes are wrong, the topology can fail when writing state, reading back changelogs, or recovering after a restart.

Example:

    Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                    "orders-count-by-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())

In this case:

- Key Serde is `StringSerde`.
- Value Serde is `LongSerde`.
- The store's changelog uses the corresponding byte formats.

If the state value is a POJO, provide a typed Serde. Example:

    Materialized
            .<String, CustomerSummary, KeyValueStore<Bytes, byte[]>>as(
                    "customer-summary"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(customerSummarySerde)

Store Serdes must stay compatible with data already written in the changelog. If you change schemas or serializers without a migration plan, new application versions may fail to restore older state.

Do not test only the fresh write path. Test restoring from a changelog containing pre-existing data, especially when upgrading application versions or schemas.

## 5. materializedAs in the Spring Cloud Stream Kafka Streams Binder

The Kafka Streams binder can materialize an incoming `KTable` binding into a state store. In that case, the `materializedAs` property on the consumer binding lets you name the store created by the binder.

Example function receiving a `KTable`:

    @Bean
    Function<KTable<String, CustomerProfile>,
             KTable<String, CustomerProfile>> enrichProfiles() {
        return profiles -> profiles.mapValues(profile ->
                profile.withDisplayName(
                        profile.firstName() + " " + profile.lastName()
                )
        );
    }

Binding configuration:

    spring:
      cloud:
        function:
          definition: enrichProfiles
        stream:
          bindings:
            enrichProfiles-in-0:
              destination: customer.profile
            enrichProfiles-out-0:
              destination: customer.profile.enriched
          kafka:
            streams:
              bindings:
                enrichProfiles-in-0:
                  consumer:
                    materializedAs: customer-profile-source-store

In this example, the input binding has type `KTable`. The binder materializes the incoming table data and uses the name `customer-profile-source-store` for the state store created by that binding. This name is useful when the application needs to query the input table's state via interactive queries.

`materializedAs` is a Kafka Streams binder binding property; it differs from calling `Materialized.as(...)` in the DSL. Use `materializedAs` when the binder creates a store for a `KTable` binding. Use `Materialized.as(...)` when the topology itself invokes aggregate/materialize operations and needs to configure the store for that output.

Do not set `materializedAs` on a `KStream` binding expecting it to automatically turn the `KStream` into a `KTable`. Input types and function signatures must match the table model. Check your binder version's behavior when bindings have multiple inputs or mix `KTable`/`GlobalKTable`.

## 6. Comparing Both Ways of Naming Stores

| Declaration | Where Used | Named Store |
|---|---|---|
| `Materialized.as("store-name")` | Kafka Streams DSL | Store for `aggregate`, `count`, `reduce`, or materialize operations |
| `consumer.materializedAs: store-name` | Kafka Streams binder | Store created by the binder for a `KTable` input binding as supported by the version |
| `destination: topic-name` | Spring Cloud Stream binding | Kafka topic read/written by the binding |
| `applicationId` | Kafka Streams application | Application identity, consumer group, and associated internal namespace |

Example of a function taking a `KTable` input and then building an additional aggregation:

    @Bean
    Function<KTable<String, CustomerProfile>,
             KTable<String, Long>> countProfilesByRegion() {
        return profiles -> profiles
                .groupBy(
                        (customerId, profile) ->
                                KeyValue.pair(profile.region(), profile),
                        Grouped.with(Serdes.String(), customerProfileSerde)
                )
                .count(
                        Materialized
                                .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                                        "customer-count-by-region"
                                )
                                .withKeySerde(Serdes.String())
                                .withValueSerde(Serdes.Long())
                );
    }

Here two stores can coexist with distinct roles:

- The input store created by the binder for the `KTable` binding and named via `materializedAs`.
- The aggregation store `customer-count-by-region` created by the DSL via `Materialized.as(...)`.

Store names must be unique within a topology. Avoid giving two distinct stores the same name, as the topology may fail to initialize or queries may hit the wrong store.

## 7. Choosing the State Store Type

Kafka Streams offers several state store types. Pick one based on how data is accessed:

| Store Type | Data Model | Scenario |
|---|---|---|
| KeyValueStore | One current value per key | Counts, sums, latest status |
| WindowStore | Multiple values per key and time window | Time-interval aggregations |
| SessionStore | State per activity session | User sessions, inactivity gaps between events |
| TimestampedKeyValueStore | Key/value paired with update timestamp | State needing last-update timestamp |
| VersionedKeyValueStore | Stores multiple timestamped versions within retention bounds | Point-in-time lookups and handling late/out-of-order records |

For instance, counting by key typically uses `KeyValueStore`. Windowed counts need a windowed store. Session aggregations use session windows and their corresponding store.

Do not force everything into a `KeyValueStore` if time-based queries are required. Conversely, a `WindowStore` adds storage overhead if the application only needs a single current value per key.

## 8. Configuring a Windowed State Store

Example counting events in 5-minute windows:

    KTable<Windowed<String>, Long> ordersPerWindow = orders
            .groupByKey(Grouped.with(
                    Serdes.String(),
                    orderEventSerde
            ))
            .windowedBy(
                    TimeWindows.ofSizeAndGrace(
                            Duration.ofMinutes(5),
                            Duration.ofMinutes(2)
                    )
            )
            .count(
                    Materialized
                            .<String, Long,
                              WindowStore<Bytes, byte[]>>as(
                                    "orders-count-by-window"
                            )
                            .withKeySerde(Serdes.String())
                            .withValueSerde(Serdes.Long())
            );

This store retains counts by key and time window. The grace period permits a window of late events to still update results under Kafka Streams' event-time semantics. The window store's retention must be long enough to cover the window duration plus the accepted late-event grace window.

Stable store names allow the topology to restore data from changelogs. If you alter window size, grace period, or key/value schemas, evaluate compatibility with old state and plan a reset/rebuild when necessary.

## 9. Logging, Changelogs, and State Restoration

State stores can be backed by a changelog topic. Kafka Streams writes state mutations to the changelog so the store can be restored when a task moves to another instance or the application restarts.

High-level flow:

    Input topic
        -> Kafka Streams task
        -> Update local state store
        -> Write changelog record
        -> Instance stops or task changes owner
        -> New instance reads changelog
        -> Restore state store
        -> Resume input processing

Changelogs are Kafka Streams' fault-tolerance mechanism. They are not a general-purpose database backup and do not replace your system's backup/retention strategy.

Some stores allow disabling logging via `Materialized` or `StoreSupplier` configuration. With changelog logging disabled, state may not recover completely after local disk loss. Only disable logging when the application can afford to rebuild state from inputs or relies on another source of truth.

Verify the following:

- Changelog topics are created properly.
- Retention and replication factors are appropriate.
- Consumers have permissions to read changelogs.
- State restoration finishes before querying stores.
- Restore time stays within availability requirements.
- Changelog schemas/Serdes remain compatible across application versions.

## 10. Persistent Stores and In-Memory Stores

Kafka Streams can use persistent or in-memory stores depending on store type and configuration. Persistent stores typically use RocksDB to store state on local disk; changelogs support recovery if local state is lost. In-memory stores keep state in process memory and may need rebuilding from changelogs/inputs after restarts.

| Characteristic | Persistent Store | In-Memory Store |
|---|---|---|
| Storage | Local disk, typically via RocksDB | RAM |
| Restart | Can reuse surviving local state plus changelog | Usually requires restore/rebuild |
| Capacity | Suits state larger than RAM | Bounded by heap/native memory |
| Latency | Incurs disk/native engine overhead | Can be fast for small datasets |
| Operations | Requires managing local state directories and disk | Requires managing memory and rebuild times |

Persistent local state does not mean state is shared across instances. Each task owns local state for its assigned partitions. When a task moves instances, state is restored from its changelog or migrated via Kafka Streams mechanics.

Do not place the local state directory on an arbitrary shared filesystem across multiple instances. Kafka Streams manages task ownership and local state per instance; sharing one directory can cause conflicts or corrupt state.

## 11. Querying State Stores with Interactive Queries

Kafka Streams supports Interactive Queries so applications can read state stores managed by the topology. In the Spring Cloud Stream Kafka Streams binder, you can use `KafkaStreamsInteractiveQueryService` to look up a store by name.

Example querying a `KeyValueStore`:

    @RestController
    public class CustomerCountController {

        private final KafkaStreamsInteractiveQueryService queryService;

        public CustomerCountController(
                KafkaStreamsInteractiveQueryService queryService) {
            this.queryService = queryService;
        }

        @GetMapping("/customers/{customerId}/order-count")
        public Long getOrderCount(@PathVariable String customerId) {
            ReadOnlyKeyValueStore<String, Long> store =
                    queryService.getQueryableStoreType(
                            "orders-count-by-customer",
                            QueryableStoreTypes.keyValueStore()
                    );

            return store.get(customerId);
        }
    }

The store name must match the name materialized in the topology. The store must be in a queryable state; while the topology is starting up or restoring, queries may not be ready yet. Actual APIs can throw exceptions if the store does not exist, has not finished restoring, or resides on a different instance.

Putting the query inside a REST controller is just an example. Production applications should handle store-not-available states, missing keys, timeouts, and errors when tasks migrate owners. Never assume one instance holds every key in the topic.

### Querying Data Residing on Another Instance

State stores are typically partitioned by task. A key may reside on a different instance from the one receiving the HTTP request. Interactive Queries provide APIs to resolve metadata/host ownership for a key and route the request to the host owning the corresponding partition.

An API can:

1. Determine the partition for the key.
2. Fetch metadata for the active host owning that store/partition.
3. Query the local store if the current host owns the key.
4. Call the owning host's internal endpoint if another host owns the key.
5. Handle host changes during rebalances with bounded retries.

Kafka Streams provides metadata APIs such as querying metadata by key/store; the Spring Cloud Stream binder may also provide query helper services. Verify exact APIs for your Kafka Streams and binder versions. Do not hardcode hostnames or assume all replicas hold identical state.

## 12. Store Names Are Part of Operations

Store names are used by the topology, interactive queries, and monitoring tools. Choose names that are:

- Stable across deployments if existing state should be restored.
- Descriptive of the aggregate or storage purpose.
- Free of pod IDs or UUIDs generated per run.
- Distinct from other stores in the same topology.
- Versioned by convention when incompatible migrations are needed.

Examples of good names:

| Name | Meaning |
|---|---|
| `orders-count-by-customer` | Order counts per customer |
| `account-balance` | Current balance per account |
| `payment-volume-by-window` | Transaction volume by window |
| `customer-profile-source-store` | State store for the input KTable |

Renaming a store can make Kafka Streams treat it as a brand-new store and create different internal changelog topics, losing access to the old local state/changelog under the prior name. Before renaming, decide whether to preserve state, rebuild from inputs, or migrate data.

## 13. Caching and State Updates

Kafka Streams can cache state updates and coalesce mutations before flushing to the state store, changelog, and downstream outputs. Caching reduces write operations and changelog record volume, especially for frequently updated keys.

Caching affects when updates become visible:

- State store queries may reflect state flushed according to lifecycle/cache boundaries rather than every individual instruction-level mutation.
- `KTable` outputs can coalesce multiple updates to the same key before emitting downstream.
- Cache size and commit interval affect latency and throughput.
- Disabling caching can increase store writes, changelog traffic, and broker load.

If an API requires immediate read-after-write semantics per request, clarify consistency/visibility guarantees and test under real cache/commit settings. Do not assume cache flush intervals act as exact SLAs without measuring.

## 14. Schema Updates and State Store Migration

State stores and changelogs have lifecycles spanning multiple application runs. Whenever you change:

- Key or value types.
- Serializers/deserializers.
- POJO schemas.
- Store names.
- Store types.
- Window sizes, retention, or aggregation semantics.

you must evaluate whether existing state remains readable.

Common migration strategies:

1. Keep wire schemas backward- and forward-compatible.
2. Create a versioned store/topic and rebuild from inputs.
3. Use a new application ID to create a clean topology namespace, then switch traffic/queries.
4. Run a controlled data migration if non-rebuildable state must be preserved.
5. Only reset state after confirming input sources can reconstruct it and an operational plan is in place.

Do not change the application ID or delete changelogs to "fix an error" without understanding the consequences. Doing so can spin up a fresh topology, reprocess old data, or lose critical state.

## 15. Testing State Stores and materializedAs

Testing must verify store creation, updates, queries, and recovery.

### Unit Testing Aggregation Operations

- Pipe multiple records with the same key.
- Assert counts/aggregates increase accurately.
- Pipe records for different keys and verify independent state.
- Verify key/value Serdes.
- Verify expected store names are declared if the test topology supports inspecting them.

### Integration Testing with Kafka

Use a test Kafka broker or Testcontainers to verify:

1. Starting up the Spring Cloud Stream Kafka Streams binder.
2. Verifying the function topology is created.
3. Publishing input records to the topic.
4. Waiting for the state store to materialize and update.
5. Querying the store by the name given in `Materialized.as` or `materializedAs`.
6. Restarting the application or shifting tasks to another instance.
7. Verifying state restoration from the changelog.
8. Checking missing-key lookups and store-not-ready handling.
9. Checking whether Serde/schema changes remain compatible with prior state.

### Testing KTable Bindings

For a `KTable` binding using `materializedAs`:

- Verify the input binding actually binds as a `KTable`.
- Verify the store name created by the binder.
- Send multiple updates for the same key and assert the store holds the latest value.
- Test tombstone/delete semantics if the topic emits `null`-valued records.
- Test interactive queries after the topology finishes restoring.

Test Binder can validate wiring at the Spring Cloud Stream level, but cannot replace real Kafka broker tests for changelogs, state restoration, task assignment, and Interactive Queries.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Store not found when querying | Query name mismatch or store not yet created/restored | Verify materialized name and topology state |
| `materializedAs` has no effect | Binding is not a `KTable` or property placed in wrong namespace | Check function signature and binder configuration |
| Aggregate fails when writing state | Missing or mismatched Serde | Configure matching key/value Serdes |
| Restart fails during state restoration | Missing changelog, retention gap, or incompatible Serde | Inspect changelog, ACLs, and schema migration |
| Querying a key returns null | Key does not exist or request hit the wrong instance | Check data and metadata/host routing |
| Different instances return different results | Querying local store on an instance not owning the key | Use Interactive Query metadata and routing |
| State store grows continuously | High key cardinality or unsuitable retention/cache settings | Review store type, retention, and data lifecycle |
| Renaming store leaves state empty | Store/changelog identity changed | Plan a migration or rebuild |
| `KTable` output updates slower than expected | Cache/commit interval or processing lag | Measure visibility latency and tune cache settings |
| Old state fails to deserialize | Breaking schema/Serde change | Version schemas and migrate state |

## 17. Checklist for Declaring State Stores

Before deploying:

1. Identify what state must be retained and which business entity the key represents.
2. Choose `KeyValueStore`, `WindowStore`, `SessionStore`, or another suitable type.
3. Determine whether the store is created by a DSL aggregation or a `KTable` input binding.
4. Use `Materialized.as(...)` for DSL operator stores.
5. Use `consumer.materializedAs` for `KTable` input bindings where supported by your binder version.
6. Choose stable, unique store names.
7. Configure compatible key/value Serdes.
8. Review changelogs, logging, retention, and local state directories.
9. Define Interactive Query APIs and routing to key-owning instances.
10. Test updates, queries, tombstones, restarts, and state restoration.
11. Plan migrations whenever changing store names or schemas.

## Conclusion

State stores hold the state Kafka Streams needs for aggregations, joins, windows, and other stateful operations. In the DSL, `Materialized.as(...)` names the store for materialized results and configures its Serdes. For `KTable` input bindings in the Kafka Streams binder, `materializedAs` can name the store created by the binder. The two mechanisms have different scopes; `destination` remains the Kafka topic, while the store name identifies internal state.

Choose the store type based on access patterns, configure key/value Serdes, understand changelogs and state restoration, and query state via Interactive Queries when needed. Keep store names and schemas stable across deployments. Test against a real Kafka broker to verify state is created, updated, queried, and restored properly after restarts or rebalances.
