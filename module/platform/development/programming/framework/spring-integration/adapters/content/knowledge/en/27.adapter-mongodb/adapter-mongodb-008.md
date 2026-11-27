# MetadataStore in MongoDB with Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Explain **`MetadataStore`** as a **key–value metadata store** for remembering technical state across polls, messages, and application restarts; distinguish it from storing business documents or Spring Messages.
- Understand the differences between an in-memory `SimpleMetadataStore`, a persistent `MetadataStore`, and a `ConcurrentMetadataStore` used across multiple threads/instances.
- Properly instantiate **`MongoDbMetadataStore`** from `MongoDatabaseFactory` or `MongoTemplate`, select the metadata collection, and register a bean named `metadataStore` when appropriate.
- Correctly use `get`, `put`, `remove`, **`putIfAbsent`**, and **`replace`**; distinguish two-step check-then-write from atomic operations.
- Use MongoDB-backed metadata for **persistent accept-once filters** in File, FTP/SFTP, and Feed adapters, as well as for **Idempotent Receiver**.
- Design namespaced keys containing environment, flow, source, and file/event identifiers; handle version changes, key collisions, and retention.
- Identify the boundary between **marking seen/claimed** and **downstream business commit**, and design retries, rollback/recovery, leases, and idempotency for reliable workflows.
- Test restarts, two instances racing for the same key, MongoDB outages, network loss, filter resets, failovers, and graceful shutdown.
- Choose appropriately among `MongoDbMetadataStore`, `MongoDbMessageStore`, MongoDB inbound adapters, change streams, and a dedicated work queue.

This lesson belongs to the **Adapter MongoDB** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. The module covers connecting external systems to Spring Integration via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; practicing flows across files, SFTP, HTTP, JMS, AMQP, Kafka, and databases with emphasis on **message contracts, errors, and connection lifecycles**. Here, MongoDB does not just store business data: it can also persist **source-tracking state** so adapters behave consistently across restarts or multiple instances.

## 1. Problem: An SFTP File Gets Re-ingested After Restart

A partner system delivers files daily via SFTP:

~~~text
/remote/orders/orders_20261123_01.csv
/remote/orders/orders_20261123_02.csv
~~~

A Spring Integration app uses an SFTP inbound adapter to download files to a local directory, turns each line into an order message, and publishes to Kafka.

A basic version using an in-memory `AcceptOnceFileListFilter` might behave like this:

~~~text
09:00  Instance A detects orders_20261123_01.csv
09:01  Filter records the seen file in A's memory
09:02  File is processed; app stops for a new deployment
09:05  Instance A' restarts; its in-memory filter starts empty
09:06  Same file still exists on SFTP → may be re-ingested
~~~

When two instances run concurrently, per-instance memory is also insufficient to coordinate:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as SFTP server
    A->>D: listFiles()
    B->>D: listFiles()
    D-->>A: orders_01.csv
    D-->>B: orders_01.csv
    Note over A,B: Neither in-memory filter has seen the file
    A->>A: acceptOnce = true
    B->>B: acceptOnce = true
    Note over A,B: Both workers may process the same data
~~~

**`MongoDbMetadataStore` solves the shared-state problem:** filters can access a persistent metadata store to record seen files/events. Multiple processes calling **`ConcurrentMetadataStore.putIfAbsent`** ensures only one process inserts a new key at a time.

However, **recording a file as seen does not mean Kafka received it or the order committed**. Crashing after marking but before processing completes remains a separate recovery problem to design for.

## 2. What MetadataStore Is, and What It Is Not

Spring Integration defines the interface:

~~~java
org.springframework.integration.metadata.MetadataStore
~~~

It provides a **`String key → String value`** contract for storing small state markers used by integration components:

- Which files have been seen and their last-modified timestamps.
- Observed timestamps/cursors on a feed or supported source.
- Whether a business event key has been accepted by an idempotent receiver step.
- The last version/value recorded for a technical marker.
- A lightweight checkpoint **if the application explicitly defines its checkpoint semantics**.

This differs from storing message payloads.

| Component | What does it store? | What is it used for? |
|---|---|---|
| **`MetadataStore`** | **String key/value** pairs | Seen state, markers, dedup/checkpoints |
| **`ConcurrentMetadataStore`** | Key/value pairs + atomic updates | Multiple threads/instances contending on keys |
| **`MongoDbMetadataStore`** | Persistent metadata in a MongoDB collection | Sharing state across restarts and instances |
| **`SimpleMetadataStore`** | In-memory metadata | Labs or transient state, lost on restart |
| **`MongoDbMessageStore`** | Spring Messages / message groups | Message store for queues/channels/aggregators per type |
| **`MongoDbChannelMessageStore`** | Messages of persistent channels | Queue-backed channels per separate contract |
| **MongoDB inbound channel adapter** | Reads business documents via polling | Emits Messages from a MongoDB collection |
| **MongoDB outbound channel adapter** | Writes business payloads to MongoDB | Persists business documents |
| **MongoDB change stream** | MongoDB change events | Emits change events via subscription |
| **MessageChannel** | Transports/routes Messages | Connects endpoints in an `IntegrationFlow` |

**Do not configure `MongoDbMetadataStore` and expect a `QueueChannel` to become durable automatically.** A persistent channel requires a compatible `MessageStore` and dedicated queue configuration. `MetadataStore` has no contract for storing `Message<?>`, headers, or payloads.

### 2.1. At What Level Does Metadata Exist?

A logical illustrative entry:

~~~text
key   = "prod|sftp-orders|/remote/orders/orders_01.csv"
value = "2026-11-23T02:00:00Z"
~~~

This is a **logical key/value illustration**, not the fixed BSON schema of `MongoDbMetadataStore`. Spring Integration may build keys/values differently depending on filter type, prefix, and version. Never manipulate internal documents directly based on a guessed structure expecting the framework to still interpret them properly.

### 2.2. When Does Persistent Metadata Help?

- The application restarts while files/feeds have not yet been deleted from the source.
- Rolling deployments run multiple instances scanning the same directory.
- A workflow needs to check whether an event key was seen previously.
- Adapters need to share simple technical state across processes.
- Moving state out of RAM onto existing durable MongoDB infrastructure.

Conversely, metadata is not the universal answer for everything: **atomic database claims**, durable brokers, outboxes, message stores, or transactions may fit better when business completion guarantees are required.

## 3. Distinguishing Three Interfaces and Two Store Types

### 3.1. Basic MetadataStore

The `MetadataStore` interface provides:

| Method | Return value | Behavior |
|---|---|---|
| `get(key)` | `String` or `null` | Reads current value; `null` if key absent |
| `put(key, value)` | `void` | Writes or overwrites value for key |
| `remove(key)` | Previous value or `null` | Deletes entry by key |

These operations are useful, yet **insufficient to prevent races** in hand-rolled "get first, then put" code.

### 3.2. ConcurrentMetadataStore

`ConcurrentMetadataStore` extends `MetadataStore` and adds two crucial operations:

| Method | Return value | When does it succeed? |
|---|---|---|
| **`putIfAbsent(key, value)`** | **`null`** if inserted; **existing value** if key already exists | Atomic at the single-key level |
| **`replace(key, oldValue, newValue)`** | **`true`** if current value matched `oldValue` and was replaced | Compare-and-set (CAS) on a single key |

Example:

~~~java
String first = store.putIfAbsent("source|file-101", "seen-by-A");
// If first == null: A inserted the entry successfully.

String second = store.putIfAbsent("source|file-101", "seen-by-B");
// second == "seen-by-A": B cannot insert the same key.

boolean updated = store.replace(
        "source|file-101", "seen-by-A", "processed");
// true when entry still holds exact value "seen-by-A".
~~~

**Do not treat `putIfAbsent(...) == null` as "the file is processed".** It only indicates the caller won the race to **record the key**.

### 3.3. Why "get then put" Is Unsafe

The following code is unsuitable for multi-instance applications:

~~~java
if (store.get(key) == null) {
    store.put(key, "seen");
    process(file);
}
~~~

Race:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant M as MongoDB MetadataStore
    A->>M: get(key) → null
    B->>M: get(key) → null
    A->>M: put(key,"seen")
    B->>M: put(key,"seen")
    Note over A,B: Both execute process(file)
~~~

Replace with:

~~~java
String previous = store.putIfAbsent(key, "seen");
if (previous == null) {
    process(file);
}
~~~

Here, the MongoDB-backed `ConcurrentMetadataStore` guarantees **inserting the key** is atomic per contract. Calling `process(file)` is a subsequent operation **not part of the same atomic MongoDB operation**.

## 4. Which API Does MongoDbMetadataStore Use?

Main class:

~~~java
org.springframework.integration.mongodb.metadata.MongoDbMetadataStore
~~~

`MongoDbMetadataStore` has been provided since Spring Integration 4.2 and **implements `ConcurrentMetadataStore`**. It stores metadata in MongoDB so multiple application instances can share state when pointed at the same database, collection, and key namespace.

Constructors provided in current APIs:

~~~java
new MongoDbMetadataStore(mongoDatabaseFactory);
new MongoDbMetadataStore(mongoDatabaseFactory, "integration_metadata");

new MongoDbMetadataStore(mongoTemplate);
new MongoDbMetadataStore(mongoTemplate, "integration_metadata");
~~~

Where:

- `mongoDatabaseFactory` has type **`org.springframework.data.mongodb.MongoDatabaseFactory`**.
- `mongoTemplate` has type **`org.springframework.data.mongodb.core.MongoTemplate`**.
- Single-argument constructors use the default collection `DEFAULT_COLLECTION_NAME`.
- Two-argument constructors allow specifying the metadata collection explicitly.
- `MongoTemplate` implements `MongoOperations`, yet this specific constructor takes **`MongoTemplate`**, not necessarily any `MongoOperations` implementation.
- This metadata store class is not a reactive MongoDB client; its operations here are synchronous/blocking.

**Version note:** legacy documentation may use the name `MongoDbFactory`. In modern Spring Data MongoDB, the Java interface is **`MongoDatabaseFactory`**. A bean named `mongoDbFactory` in XML does not mean the old Java interface is still in use.

## 5. Adding Dependencies and Connecting to MongoDB

### 5.1. Maven for Spring Boot 3.x

For Spring Boot 3.x applications managing versions via a compatible BOM:

~~~xml
<!-- Dependencies inside <dependencies> of pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

File/SFTP filters require their respective adapter dependencies if practicing those parts, e.g., `spring-integration-file` or `spring-integration-sftp`. In Spring Boot apps, pull those modules via compatible starters/managed dependencies. **An SFTP server is not required to learn the basic `MetadataStore` API.**

If your project uses a different Spring Boot or Spring Integration major version, verify BOM/imports and compatible drivers. This lesson focuses on **blocking `MongoDbMetadataStore`**, without arbitrarily mixing reactive drivers.

### 5.2. Local MongoDB URI

In `application.yml` for Spring Boot 3.x:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/integration_lab
~~~

This is a **test database**. In production, use a secret manager/environment variables, TLS, and appropriately scoped MongoDB permissions. If Boot already provides `MongoDatabaseFactory` and `MongoTemplate`, inject them instead of creating another `MongoClient` inside each filter.

## 6. Configuring the MongoDbMetadataStore Bean in Java

### 6.1. Registering a Bean Named metadataStore

Practical configuration:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.mongodb.metadata.MongoDbMetadataStore;

@Configuration
public class MongoMetadataConfiguration {

    @Bean("metadataStore")
    public ConcurrentMetadataStore metadataStore(
            MongoDatabaseFactory mongoDatabaseFactory) {

        return new MongoDbMetadataStore(
                mongoDatabaseFactory, "integration_metadata");
    }
}
~~~

Meaning:

1. `MongoDatabaseFactory` specifies the actual MongoDB database/connection.
2. `"integration_metadata"` is a **dedicated collection for technical state**; do not mix it with business telemetry/order collections.
3. `ConcurrentMetadataStore` is the interface sufficient for persistent accept-once filters and idempotent receivers.
4. The bean name **`metadataStore`** is the convention allowing **components that auto-lookup a `MetadataStore`** to discover the shared bean.
5. Not every adapter automatically picks up the bean solely by naming convention. For filters, **inject/wire the store explicitly** to guarantee where state is written.
6. Other instances sharing state must use **the same MongoDB deployment/database/collection and key scheme**.

When you need a separate metadata store for another workload or environment, give it a distinct bean name and inject via `@Qualifier`. Avoid having two beans with the same name where only one gets wired silently.

### 6.2. Configuring from MongoTemplate

If a Spring Boot–managed `MongoTemplate` bean already exists:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.mongodb.metadata.MongoDbMetadataStore;

@Bean("metadataStore")
public ConcurrentMetadataStore metadataStore(
        MongoTemplate mongoTemplate) {

    return new MongoDbMetadataStore(
            mongoTemplate, "integration_metadata");
}
~~~

**This is an alternative to section 6.1**; do not declare both `metadataStore` beans in the same context. `MongoDbMetadataStore` uses whatever database/driver settings the template has.

### 6.3. Default Collection or Explicitly Named Collection?

You can use the single-argument factory/template constructor to keep `DEFAULT_COLLECTION_NAME`, but in real environments **an explicit collection name is easier to operate**:

~~~text
Database: integration_lab
Collection: integration_metadata
Keys:
  prod|orders-sftp|/remote/orders/orders_01.csv
  prod|invoice-idempotency|invoice-123
~~~

The collection name does not grant permissions by itself: the MongoDB account must be authorized to operate on that collection. Keep the metadata collection separate from business documents and message stores to avoid unintended retention or migration actions.

## 7. API get, put, putIfAbsent, replace, remove by Example

### 7.1. Service Class Exercising Metadata Operations

~~~java
package example.mongodb;

import java.util.Objects;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.stereotype.Service;

@Service
public class MetadataExampleService {

    private final ConcurrentMetadataStore store;

    public MetadataExampleService(
            ConcurrentMetadataStore store) {
        this.store = store;
    }

    public boolean firstSeen(String source, String eventId) {
        String key = "demo|v1|" + source + "|" + eventId;
        return store.putIfAbsent(key, "SEEN") == null;
    }

    public String getStatus(String source, String eventId) {
        return store.get("demo|v1|" + source + "|" + eventId);
    }

    public boolean advanceStatus(
            String source, String eventId,
            String expected, String next) {

        Objects.requireNonNull(expected);
        Objects.requireNonNull(next);
        String key = "demo|v1|" + source + "|" + eventId;

        return store.replace(key, expected, next);
    }

    public String removeMarker(String source, String eventId) {
        String key = "demo|v1|" + source + "|" + eventId;
        return store.remove(key);
    }
}
~~~

**Example limitations:** `source`/`eventId` must be validated before forming keys; never let overly long inputs or unexpected delimiters alter the namespace. This example only illustrates metadata APIs and **does not implement a safe claim/lease/ACK workflow**.

### 7.2. Sequence of Operations

Suppose a key does not yet exist:

~~~text
get("demo|v1|sftp|evt-101")                 -> null

putIfAbsent("demo|v1|sftp|evt-101","SEEN") -> null
get(...)                                    -> "SEEN"

putIfAbsent("demo|v1|sftp|evt-101","SEEN") -> "SEEN"

replace("demo|v1|sftp|evt-101",
        "SEEN","DONE")                       -> true

replace("demo|v1|sftp|evt-101",
        "SEEN","FAILED")                     -> false

remove("demo|v1|sftp|evt-101")             -> "DONE"
get(...)                                    -> null
~~~

When `putIfAbsent` returns `null`, the caller won the right to **insert the key**. When `replace` returns false, either the value changed, the key was removed, or `expectedValue` did not match; handle this as a **CAS conflict**, never blindly overwriting with `put`.

### 7.3. put Behavior Differs from putIfAbsent

`put(key, value)` **writes or updates** the entry unconditionally regardless of prior value. It suits admin markers or latest-value updates when the app owns the write, but **must not be used to acquire exclusive processing rights**.

~~~java
store.put("source|checkpoint", "offset-200");
store.put("source|checkpoint", "offset-150");
// Without a guard, the checkpoint regressed from 200 back to 150.
~~~

If an offset/cursor must advance monotonically, use comparison logic and **compare-and-set** with conflict retries. Never assume the metadata store understands ordering inside String offsets; that is a business rule.

### 7.4. remove Is Not Compare-and-Delete

`remove(key)` deletes a key by name without taking an expected value. If owners/leases are changing, an unconditional `remove` can accidentally delete another worker's fresh marker.

If you need "only the current owner may release", use a conditional protocol and/or an appropriate database mechanism. Never call `remove` blindly inside an error handler without knowing whether the key now belongs to another worker.

## 8. Why MongoDbMetadataStore Is Safer Than Local Memory Across Multiple Instances

### 8.1. Shared State

Two instances must point to the same database/collection:

~~~mermaid
flowchart LR
    A["Spring Instance A"] --> F1["SFTP persistent filter"]
    B["Spring Instance B"] --> F2["SFTP persistent filter"]
    F1 --> M["MongoDbMetadataStore<br/>shared collection"]
    F2 --> M
    M --> DB[("MongoDB")]
    F1 --> C["MessageChannel"]
    F2 --> C
~~~

When filters/selectors run `putIfAbsent` or `replace` on **the same key**, only one operation wins under the atomic contract. There is no coordination benefit if Instance A uses collection `integration_metadata_a` while B uses `integration_metadata_b`, or if the two instances construct different keys for the same file.

### 8.2. Atomic Key Operation ≠ Distributed Transaction

Separate two concepts:

- **Atomic on the entry:** inserting a new key or swapping a value when `expectedValue` matches.
- **End-to-end business completion:** fully downloading the file, parsing, saving to the target database, sending to Kafka/JMS, and confirming business completion.

An atomic metadata operation **does not span** HTTP, SFTP, Kafka, or JMS steps. If a file is marked `SEEN` and then the thread crashes before sending the message, the chance to reprocess may be lost if the filter trusts the persisted marker forever.

### 8.3. MetadataStore Does Not Automatically Become a Complete Distributed Lock

You can build an owner/lease protocol on top of metadata key/values, but you must handle:

- Lease expiration and clock skew between nodes.
- Who is authorized to update/release keys.
- A process pausing for a long time and resuming work after its lease expired.
- Fencing tokens if external side effects must reject stale owners.
- Stuck keys caused by crashes and how to reclaim them.
- Ensuring a request is considered complete only after business commit.

If the workload is a MongoDB work queue needing atomic document claiming, **`findAndModify` on status/lease** or a durable message broker may fit better than a bare `MetadataStore`.

## 9. Persistent Accept-Once Filter for the File Inbound Adapter

### 9.1. In-Memory Default Filter vs. Persistent Filter

A basic `AcceptOnceFileListFilter` remembers accepted files in process memory. After restart, RAM state vanishes. When the source does not delete or move files, the same files can be reprocessed.

`FileSystemPersistentAcceptOnceFileListFilter` accepts a `ConcurrentMetadataStore` and a prefix to persist file state:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.file.filters.FileSystemPersistentAcceptOnceFileListFilter;
import org.springframework.integration.metadata.ConcurrentMetadataStore;

@Bean
public FileSystemPersistentAcceptOnceFileListFilter localFileFilter(
        ConcurrentMetadataStore metadataStore) {

    return new FileSystemPersistentAcceptOnceFileListFilter(
            metadataStore, "prod|file-import|");
}
~~~

The filter can record **path name and file last-modified time**; a file whose modified time changes may be treated as a new version and accepted again per filter contract.

**Prefixes prevent collisions:** two different ingestion flows might both see a file named `orders.csv`. If they accidentally share the same key namespace, Flow A's acceptance state blocks Flow B.

### 9.2. Attaching the Filter to FileReadingMessageSource

Example source reading files from local disk:

~~~java
package example.mongodb;

import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.FileReadingMessageSource;
import org.springframework.integration.file.filters.FileSystemPersistentAcceptOnceFileListFilter;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class LocalFileInboundConfig {

    @Bean("importFiles")
    public MessageChannel importFiles() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow importLocalFiles(
            FileSystemPersistentAcceptOnceFileListFilter localFileFilter) {

        FileReadingMessageSource source =
                new FileReadingMessageSource();
        source.setDirectory(new File("data/incoming"));
        source.setFilter(localFileFilter);

        return IntegrationFlow
                .from(source,
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(5000)
                               .maxMessagesPerPoll(10)))
                .channel("importFiles")
                .get();
    }
}
~~~

**Prerequisites:** the `data/incoming` directory exists and is readable, `importFiles` has a consumer accepting `java.io.File`, and the app includes the `spring-integration-file` dependency. The relative path above is for labs only; production requires absolute paths and permission checks.

`maxMessagesPerPoll(10)` caps how many times the source receives messages per poll task, **not** the number of metadata keys in the collection. With multiple consumers or threads, test source/filter coordination and file lifecycle policies.

### 9.3. A Seen File Can Change

Persistent accept-once file filters generally use filename/path and last-modified time as identifying metadata; if a file is overwritten or its timestamp changes, the filter may accept it again. This **differs from unique-content hashing**.

If business rules require "immutable files ingested once", add checksums or business file IDs in the processing layer. If files may be updated after upload to SFTP, define a naming/mtime/atomic-rename contract to avoid reading partially written files.

## 10. MongoDB MetadataStore with SFTP / FTP Inbound

SFTP inbound has two layers:

1. **Remote filter** decides which files on SFTP should be downloaded.
2. **Local filter** decides which local files should be emitted as Spring Messages.

~~~mermaid
flowchart LR
    S["SFTP remote directory"] --> RF["SftpPersistentAcceptOnceFileListFilter"]
    RF -->|"Select file"| DL["Download/synchronize"]
    DL --> L["Local directory"]
    L --> LF["FileSystemPersistentAcceptOnceFileListFilter"]
    LF --> C["MessageChannel<File>"]
    RF --> M["Shared MongoDbMetadataStore"]
    LF --> M
~~~

**Separating remote/local state matters:** a file may be downloaded yet not dispatched to a handler, or dispatched to a handler that fails downstream. The two filters do not form an automatic transaction across all stages.

### 10.1. Remote SFTP Filter Using the Shared MongoDB Store

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.sftp.filters.SftpPersistentAcceptOnceFileListFilter;

@Bean("remoteOrdersFilter")
public SftpPersistentAcceptOnceFileListFilter remoteOrdersFilter(
        ConcurrentMetadataStore metadataStore) {

    return new SftpPersistentAcceptOnceFileListFilter(
            metadataStore, "prod|sftp-remote-orders|");
}
~~~

Wire this filter into the **remote filter** of the SFTP inbound synchronizer/adapter—for example XML attribute `filter`, or the equivalent Java DSL/API for your version. Wire `FileSystemPersistentAcceptOnceFileListFilter` separately as the **local filter** via `local-filter`.

If both filters share one collection, use distinct prefixes so the same file is not mistaken for already accepted at the other layer.

### 10.2. XML Wiring Example

Illustrative wiring referencing filter beans declared in the Spring context:

~~~xml
<!-- XML must declare int and int-sftp namespaces, sessionFactory, and channel -->
<int-sftp:inbound-channel-adapter
        id="ordersSftpInbound"
        session-factory="sftpSessionFactory"
        channel="importFiles"
        remote-directory="/remote/orders"
        local-directory="file:./data/orders"
        filter="remoteOrdersFilter"
        local-filter="localOrdersFilter"
        max-fetch-size="10">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="10"/>
</int-sftp:inbound-channel-adapter>
~~~

Where:

- `remoteOrdersFilter` is the `SftpPersistentAcceptOnceFileListFilter` bean.
- `localOrdersFilter` is the `FileSystemPersistentAcceptOnceFileListFilter` bean with a **different** prefix.
- `sftpSessionFactory` is supplied by the application using controlled credentials/host keys.
- `importFiles` is the channel with a consumer accepting `File` payloads.
- `max-fetch-size` caps remote files downloaded per synchronization run per adapter API.
- `max-messages-per-poll` caps `File` Messages emitted in one poll task.
- `max-fetch-size` and `max-messages-per-poll` **do not mean the same thing**; tune them based on file size, queue/backlog, and concurrency.

This XML configuration is an **alternative** to the local File inbound flow in section 9; do not register two endpoints competing over the same directory when you only want one pipeline.

### 10.3. Important Note on SFTP Failures and Retries

With remote persistent file filters, files can be recorded in metadata **before download**. When a transfer fails, reversible filters can roll back on transfer errors. **However, downstream failures after the file has downloaded and been emitted as a message generally do not auto-delete remote/local markers.**

Example:

~~~text
SFTP remote accept → metadata marks seen
    ↓
Download completes → local file
    ↓
Local filter emits File Message
    ↓
Kafka publish fails → downstream not committed
    ↓
Seen marker may still remain
~~~

Therefore, never claim "because we use a persistent filter, no data can be lost and no retries are needed". To reprocess on downstream failure, design explicit filter rollback/reset, business state tracking, or a separate durable queue per error type.

**Version difference:** starting in Spring Integration 7.0, persistent file list filters use keys with **longer paths** (source directory path + filename) to reduce collisions when two files share a name in different directories. When upgrading major versions, plan migration of legacy keys to avoid unintended re-fetches or skipped files.

## 11. Idempotent Receiver Using MongoDbMetadataStore

### 11.1. Why Is an Idempotent Receiver Needed?

A Kafka/JMS/AMQP/HTTP/UDP integration flow can receive the same event multiple times due to retries, redeliveries, or duplicate client submissions. Even if the source has a broker checkpoint, downstream should use a **durable business event key** to detect duplicates.

Example:

~~~json
{
  "eventId": "evt-101",
  "tenantId": "tenant-a",
  "type": "READING_CREATED",
  "deviceId": "node-7"
}
~~~

Never use Spring's `MessageHeaders.ID` as a business dedup key: a redelivered event can be wrapped in a new message with a different UUID.

### 11.2. MetadataStoreSelector

Spring Integration provides `MetadataStoreSelector`: from a request `Message`, the selector derives a key and calls `ConcurrentMetadataStore.putIfAbsent`. If the key is absent, the message is accepted; if it already exists, it is treated as a duplicate per default policy.

Example:

~~~java
package example.mongodb;

public record BusinessEvent(
        String tenantId,
        String eventId,
        String type) {
}
~~~

Configuring the selector and interceptor:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;

@Configuration
public class DeduplicationConfig {

    @Bean("deduplicateAdvice")
    public IdempotentReceiverInterceptor deduplicateAdvice(
            ConcurrentMetadataStore metadataStore) {

        MetadataStoreSelector selector =
            new MetadataStoreSelector(message -> {
                BusinessEvent event =
                        (BusinessEvent) message.getPayload();

                if (event.tenantId() == null
                        || event.eventId() == null
                        || event.eventId().isBlank()) {
                    throw new IllegalArgumentException(
                            "Missing stable event identity");
                }

                return "prod|events|v1|"
                        + event.tenantId()
                        + "|" + event.eventId();
            }, metadataStore);

        IdempotentReceiverInterceptor advice =
                new IdempotentReceiverInterceptor(selector);

        // Prevent duplicates from reaching the business handler.
        advice.setDiscardChannelName("nullChannel");
        return advice;
    }
}
~~~

Then attach it to a `@ServiceActivator` endpoint:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IdempotentReceiver;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageHandler;

@Configuration
public class BusinessEventHandlerConfig {

    @Bean
    @ServiceActivator(inputChannel = "rawBusinessEvents")
    @IdempotentReceiver("deduplicateAdvice")
    public MessageHandler businessHandler() {
        return message -> {
            BusinessEvent event =
                    (BusinessEvent) message.getPayload();

            // Invoke processing service with contract and idempotency.
            System.out.println("Processing " + event.eventId());
        };
    }
}
~~~

This illustrative code requires a `rawBusinessEvents` channel, producer, dependencies, and consumer wiring in the same Spring context. The handler currently only logs—**there is no real business commit**.

### 11.3. Default Pitfall of IdempotentReceiverInterceptor

When the interceptor has **no** `discardChannel` and `throwExceptionOnRejection` is not enabled, duplicates **may still be passed to the handler**, tagged with a `duplicateMessage=true` header for the handler to decide.

If the goal is blocking duplicates **before the handler runs**, configure a discard channel (such as `nullChannel`) or an appropriate rejection policy. Never read "IdempotentReceiver" and assume duplicates are automatically dropped by default.

### 11.4. When the Selector Records the Key but the Handler Fails

Sequence:

~~~text
MetadataStoreSelector.accept(event)
  → putIfAbsent(eventKey, value) succeeds
  → business handler starts
  → target service fails / process crashes
  → key still exists
  → redelivery is treated as a duplicate
~~~

**This is the premature-marking risk.** Standard `MetadataStoreSelector` is primarily an **acceptance filter**, not a distributed transaction manager across Kafka + MongoDB + HTTP.

For events that must never be lost, design:

- Persist `PROCESSING/DONE/RETRY` state keyed by event ID.
- Mark `DONE` only after business commit is confirmed.
- Use leases/timeouts to recover stuck `PROCESSING` keys.
- Enforce idempotency at the target to handle cases where the target committed but the response was lost.
- Use a durable broker/outbox or properly scoped database transaction when needed.
- Never blindly delete the key on every exception if another worker could have just reclaimed it via CAS.

### 11.5. compareValues and Version Handling

`MetadataStoreSelector` can be configured with a `BiPredicate<String,String>` via `compareValues(...)` when you want to accept **newer values** instead of rejecting every message sharing a key.

Theoretical example: the key is a file ID and the value is an update sequence number. The selector can accept a higher version and swap metadata with CAS. However, **string comparison semantics must be explicitly defined**—never use arbitrary lexicographic comparison for numbers like `"9"` and `"10"`.

For foundational lessons, `putIfAbsent` is clearer and safer; enable `compareValues` only after building concurrency and version-semantics tests.

## 12. MetadataStore Differs from MongoDB Inbound Polling State

This point relates directly to the Adapter MongoDB chapter:

- **`MongoDbMessageSource`** periodically queries a collection for documents with `status=NEW`.
- **`MongoDbMetadataStore`** is a key/value store used by filters/selectors or application code.
- **Simply registering a `metadataStore` bean does not make `MongoDbMessageSource` track "already polled documents".**

Example query:

~~~javascript
db.inbox_events.find({ status: "NEW" })
~~~

If `MongoDbMessageSource` runs every 5 seconds without updating document status, it will keep seeing the same documents. Having a `MongoDbMetadataStore` in the Spring context **does not alter that query**.

To avoid duplicate reads:

1. Design MongoDB query/update/claim directly on the source document, e.g., `NEW → PROCESSING → DONE`.
2. Or place a filter/selector after the source using stable metadata keys, **paired with a retry policy for downstream failures**.
3. If multiple instances must process documents exclusively, prefer conditional `MongoOperations.findAndModify` with leases over two-step read-then-write.
4. If you need every change from MongoDB, consider change streams + dedicated resume tokens/checkpoints.

**Do not treat `MetadataStore` as an automatic cursor for the MongoDB inbound adapter.** A relationship exists only when the application explicitly **configures** an endpoint to use metadata.

## 13. Designing Key Namespaces, Values, and Retention

### 13.1. Keys Should Be Stable and Contextual

A well-structured key can include:

~~~text
<environment>|<application>|<flow>|<source>|<identity>
~~~

Examples:

~~~text
prod|ingestion|sftp-orders|partner-a|/remote/orders/2026-11-23.csv
prod|ingestion|file-local|site-3|D:/incoming/order-101.csv
prod|ingestion|idempotent|tenant-a|evt-101
~~~

`"prod"`, `"ingestion"`, and `"tenant-a"` here are **illustrative values**, not mandatory framework strings. Standard filters append prefixes/paths/timestamps per their own contract; never inject extra components that alter internal filter keys without verifying implementation/version details.

### 13.2. Common Key Namespace Mistakes

| Mistake | Consequence |
|---|---|
| Two flows share a prefix with different meanings | Key collisions; files/events get skipped by mistake |
| Different prefixes on instances A and B for the same logical source | Instances fail to coordinate; duplicates |
| Key includes message receive timestamp | Redelivery gets a new timestamp; dedup breaks |
| Key omits tenant/source | Identical keys collide across tenants |
| Key embeds secrets/tokens | Sensitive data leaks in metadata/logs/backups |
| Key uses unnormalized file paths | Two representations of the same logical path become two keys |
| Key format changes during filter upgrade | Unexpected re-fetches or old state ignored |
| Overly long keys or mixed characters | Difficult operations/monitoring/backups |
| Value stores large payloads | Misuse of metadata store; bloats MongoDB |

### 13.3. How Long Should Metadata Be Retained?

A persistent store has no automatic "forget after 30 days" business rule. If millions of file/event IDs arrive daily, the collection grows unbounded without retention.

You must decide:

- Maximum window during which the source may redeliver/replay data.
- How long deduplication is required before reprocessing is acceptable.
- Audit, legal, backup, and disaster recovery requirements.
- How to handle a file whose mtime changes while its name stays identical.
- How to purge entries **without triggering mass reprocessing**.

**Never create a TTL index on your own** based on a guessed field in `MongoDbMetadataStore`'s schema. If TTL is desired, inspect the actual schema for your version and design retention at the application or custom store layer; MongoDB TTL deletion runs as a background task and does not replace precise lease expiration.

### 13.4. Changing a Prefix Is a Migration

Suppose old keys used `prod|sftp-orders|...` and a new release changes to `prod|sftp-v2|...`. To `MetadataStore`, those are **two distinct namespaces**. The new filter will not see previously recorded files.

Therefore, when changing prefixes, path formats, adapter versions, or collections, plan to:

1. Back up metadata state.
2. Document old and new key formats.
3. Test on a cloned database with both seen and unseen files.
4. Execute a controlled migration/compatibility policy.
5. Monitor duplicates/replays after rollout.
6. Never delete old metadata until results are verified.

## 14. Errors, Retries, and Crash Recovery

### 14.1. Boundaries in the Workflow

An SFTP → MongoDB metadata → Kafka pipeline has these milestones:

~~~text
A. SFTP file appears
B. Persistent filter sets "seen" marker
C. File is downloaded locally
D. File Message is emitted on MessageChannel
E. Handler parses/validates into order events
F. Target Kafka or DB confirms write
G. Business status completes and ACK per contract
~~~

The marker at step **B** does not prove **F/G** succeeded. If the process crashes between B and G, you need recovery mechanisms: rescanning local files, business checkpoints, requeuing, controlled filter resets, or idempotent downstream reprocessing.

### 14.2. Failure Modes Table

| Failure | Situation | What to design |
|---|---|---|
| MongoDB unavailable | `putIfAbsent`/`replace` throws exception | Fail closed or bounded retry; never bypass filter by default |
| Network timeout writing metadata | Unknown whether server wrote it | Re-read/use the same key to reconcile; never invent a new key |
| Key recorded, download failed | File incomplete | Remote filter rollback per contract where supported; test behavior |
| Key recorded, handler failed | Downstream uncommitted | Replay/recovery to avoid accidental at-most-once |
| Message sent, ACK lost | Target may have processed it | Stable event ID, idempotent downstream |
| Worker A dies after claim | `PROCESSING` key stuck | Lease/owner/expiry or recovery job |
| Worker A wakes up after lease expired | Stale owner still running | Fencing/version check before side effects |
| Two workers pick the same file | Source contention | Shared metadata store, matching prefix, atomic keys |
| MongoDB failover | I/O errors / write concern uncertainty | Retry budget, consistency, topology checks |
| Metadata collection deleted | Seen state lost | Backup/restore, restrict delete rights, replay plan |
| Prefix/filter version changed | Old state unrecognized | Migration and restart testing |
| Key count spikes | Large storage/index footprint | Controlled retention and metrics |

### 14.3. Fail-Open or Fail-Closed Policy?

If `MetadataStore` becomes unreachable:

- **Fail-open**: let messages continue without dedup checks; risks duplicate side effects.
- **Fail-closed**: reject or pause accepting new messages; reduces duplicate risk at the cost of availability.

No single policy fits every workload. For operations risking duplicate billing or duplicate commands, **fail-closed or durable retry** is usually safer. If the source is durable and downstream is idempotent, other trade-offs may work.

**Avoid catching `Exception` and treating it as "key absent".** `MetadataStore.get(key) == null` and MongoDB failing to respond are **two completely different states**.

## 15. Transactions, CAS, Leases, and Exactly-Once

### 15.1. CAS Guarantees Metadata State on One Key Only

A CAS operation:

~~~java
boolean advanced = store.replace(
        "event|evt-101",
        "PROCESSING:worker-a",
        "DONE");
~~~

succeeds only if the key currently holds that exact old value. It does not:

- Commit a Kafka offset.
- Send an HTTP request and await an ACK.
- Mark an SFTP file as deleted from the server.
- Create a transaction spanning MongoDB and JMS.
- Guarantee exactly-once business side effects in another system.

### 15.2. Why remove After an Exception Is Dangerous

Suppose Worker A writes `PROCESSING:A` and then pauses for a long time. Worker B follows a valid lease protocol to reclaim ownership as `PROCESSING:B`. If A wakes up and calls unconditional `remove(key)`, A **deletes B's active key**.

Because `MetadataStore.remove(key)` takes no expected value, avoid using it as an "owner lock release" in complex protocols. Design conditional transaction/document deletes or use a dedicated lock service with fencing if needed.

### 15.3. When MongoDB Transactions Are Needed

If business logic must update multiple MongoDB documents atomically, you need a supported MongoDB topology and `MongoTransactionManager` with proper transaction boundaries. `MongoDbMetadataStore` by itself **does not create a transaction spanning business collections, brokers, or HTTP** merely because both use MongoDB.

Even MongoDB multi-document transactions do not provide distributed exactly-once semantics across SFTP, Kafka/JMS, HTTP, or the filesystem. When cross-system durability is required, consider **outbox, durable inbox, idempotent consumers, state machines, and reconciliation**.

## 16. Testing the Basic API Against Real MongoDB

### 16.1. Testing get/put/replace/remove and Restart Behavior

Use a **dedicated test MongoDB instance** or Testcontainers when Docker is available. JUnit 5 example with Spring Boot Test and a test database:

~~~java
package example.mongodb;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.integration.mongodb.metadata.MongoDbMetadataStore;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoDbMetadataStoreIT {

    @Autowired
    MongoDatabaseFactory mongoDatabaseFactory;

    @Test
    void survivesRecreatingStoreObject() {
        String key = "it|metadata|" + UUID.randomUUID();

        MongoDbMetadataStore first = new MongoDbMetadataStore(
                mongoDatabaseFactory, "integration_metadata_test");
        MongoDbMetadataStore second = new MongoDbMetadataStore(
                mongoDatabaseFactory, "integration_metadata_test");

        try {
            assertNull(first.get(key));

            assertNull(first.putIfAbsent(key, "SEEN"));
            assertEquals("SEEN", second.get(key));

            assertEquals("SEEN",
                    second.putIfAbsent(key, "OTHER"));

            assertFalse(second.replace(
                    key, "WRONG", "DONE"));

            assertTrue(second.replace(
                    key, "SEEN", "DONE"));

            assertEquals("DONE", first.get(key));
            assertEquals("DONE", first.remove(key));
            assertNull(second.get(key));
        } finally {
            first.remove(key);
        }
    }
}
~~~

This test creates **two store objects pointing to the same MongoDB collection**, proving state is not trapped in the first Java object's memory. It **does not by itself prove survival across a real process restart**; the lab exercise restarts the Spring context or app and reads the key back.

**Never run against a production database** because the test writes and deletes metadata. Only clean up keys carrying the test's own prefix/UUID.

### 16.2. Testing Two Workers Racing for the Same Key

Run two threads using two store objects against the same database:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.junit.jupiter.api.Assertions.*;

void assertOneWinner(
        MongoDbMetadataStore storeA,
        MongoDbMetadataStore storeB,
        String key) throws Exception {

    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch gate = new CountDownLatch(1);

    try {
        Future<String> a = pool.submit(() -> {
            gate.await();
            return storeA.putIfAbsent(key, "A");
        });

        Future<String> b = pool.submit(() -> {
            gate.await();
            return storeB.putIfAbsent(key, "B");
        });

        gate.countDown();

        int winners = (a.get() == null ? 1 : 0)
                    + (b.get() == null ? 1 : 0);

        assertEquals(1, winners);
    } finally {
        pool.shutdownNow();
    }
}
~~~

This snippet is a **helper method**, not a complete test class. Tests must use a **non-existent key** and remove that exact key afterward; if the key pre-existed, both calls return the old value and neither wins. If the test runner disallows threads or MongoDB drops out, investigate the failure rather than immediately claiming the store lacks atomicity.

### 16.3. Testing putIfAbsent vs. put

In a separate test:

~~~java
store.put("it|cursor|123", "100");
assertEquals("100", store.get("it|cursor|123"));

store.put("it|cursor|123", "90");
assertEquals("90", store.get("it|cursor|123"));
~~~

This demonstrates `put` can overwrite values and regress checkpoints unless guarded by the app. **Never use fixed literal keys in parallel tests**; include a UUID/prefix to avoid colliding with other test runs.

## 17. Testing Persistent File Filters and Restarts

### 17.1. Testing the Filter on a Local File

With `FileSystemPersistentAcceptOnceFileListFilter`, create a temporary file at a unique path inside a **test directory** and verify:

1. Filter A accepts the file the first time.
2. Filter A rejects the file the second time when mtime is unchanged.
3. Instantiate a new **Filter B** using the same `MongoDbMetadataStore` collection/prefix.
4. Filter B still rejects the file: proving the marker persists beyond the filter instance.
5. Update the modified time in a controlled way.
6. Verify the filter handles the modified file per your version's contract.
7. Invoke the filter reset API or clean up **only the test key** when needed.
8. Start a fresh app process and re-run to verify real persistence.

If the filter was mistakenly configured with `SimpleMetadataStore`, the restart test will fail because markers are not persisted in MongoDB.

### 17.2. Testing Independent SFTP Remote and Local Filters

Using a test SFTP server and test MongoDB instance:

- Seed a file on remote with a stable path/mtime.
- Verify one instance downloads the file, and a second instance sharing remote metadata does not re-download an unchanged file as expected.
- Verify the local filter does not re-emit already-processed files across restarts when backed by the persistent store.
- Simulate a partial download failure: observe remote filter rollback if supported by the implementation.
- Simulate a handler error **after download completes**: do not assume the marker is automatically removed.
- Modify remote mtime to test how changed files are detected.
- Place two identically named files in two different directories, especially when upgrading to Spring Integration 7.x.
- Verify remote/local prefixes do not collide and both instances share the same key scheme.
- When using `maxFetchSize`, test how multiple instances behave scanning the same remote directory.

**Accepting a file once does not prove business ACK completed.** Tests should assert both filter state and actual records committed to Kafka/target DB.

## 18. Observability and Managing the Metadata Collection

Suggested metrics (do not assume Spring Integration emits these exact names automatically):

| Metric | Purpose |
|---|---|
| `metadata_get_total` | State read count |
| `metadata_put_if_absent_total` | Attempts to claim a new key |
| `metadata_put_if_absent_won_total` | Successful insertions |
| `metadata_duplicate_detected_total` | Existing-key detections |
| `metadata_cas_conflicts_total` | Failed `replace` calls due to mismatched values |
| `metadata_operation_latency_seconds` | MongoDB metadata I/O latency |
| `metadata_operation_errors_total` | Query/write/auth/network errors |
| `metadata_collection_documents` | Entry count and growth trend |
| `metadata_expired_or_removed_total` | Retention/recovery cleanups |
| `file_remote_fetch_failures_total` | Remote file download errors |
| `file_downstream_processing_errors_total` | Errors after file acceptance |
| `idempotent_rejected_total` | Duplicates blocked |
| `business_committed_total` | Business events truly completed |

**Distinguish:** metadata marker counts, emitted `File` Messages, parsed events from files, and successful business transactions can differ significantly.

### 18.1. Capacity and Indexes

Because metadata resides in a MongoDB collection, track document counts, index sizes, and key access latency. The API docs do not ask users to guess internal schemas and add arbitrary indexes. If optimization is needed, inspect the actual collection created by your deployed version, review query plans/existing indexes, and plan migrations carefully.

With stable key namespaces, sensible retention, backups, and MongoDB monitoring, `MetadataStore` can run long-term without bulk manual metadata fixes.

### 18.2. Read/Write Concern and Failover

An atomic MongoDB operation does not offer identical durability across failover under every **write concern/read concern**. When metadata prevents duplicate side effects across nodes, evaluate replica-set topology, appropriate write concerns, timeouts, and lost-response scenarios.

When a write outcome is ambiguous, **reuse the exact same key** and reconcile state rather than generating a new key per attempt. Never "fall back" to a local in-memory metadata store unless duplicates are acceptable.

### 18.3. Backups, Restores, and Version Upgrades

Back up metadata alongside related business checkpoints. If business data is restored to a different point in time than metadata, mismatches occur:

- **Metadata too new:** files/events not actually committed in the restored data are treated as already seen.
- **Metadata too old:** already-committed files/events are reprocessed.

Therefore, maintain a **consistent recovery plan**, testing replays and idempotency. Never assume a standalone metadata backup suffices to recover the entire pipeline.

## 19. Securing the MongoDB Metadata Store

- Apply **least privilege**: grant the account permissions only on the **metadata collection**, not blanket read/write access to all business collections.
- Store URIs/credentials in a secret manager or environment variables; enable TLS where appropriate.
- Never embed tokens, passwords, sensitive info, or personal payloads inside metadata keys/values.
- Do not log full keys if customer paths/tenant IDs are sensitive; hash or mask portions as needed.
- Prevent HTTP/Kafka/SFTP clients from controlling prefixes/key namespaces to hijack others' keys.
- Enforce backup/retention/audit policies and strict **delete/drop collection** permissions.
- Bound how many keys a single request can create to prevent metadata cardinality explosion.
- Set timeouts/circuit breakers/retry budgets for MongoDB metadata I/O so stalls do not freeze the entire poller.
- In multi-tenant setups, assess whether one shared metadata collection satisfies tenant isolation or if separate factories/databases with distinct permissions are required.
- Ensure monitoring avoids high-cardinality labels per key/file/event ID.

**Never assume "using MongoDB" means "secure by default".** Security depends on roles, what goes into keys/values, credential handling, and recovery procedures.

## 20. Common Errors and How to Isolate Them

| Symptom | Possible cause | How to check |
|---|---|---|
| Files re-ingested after restart | Filter still using `SimpleMetadataStore` | Inject persistent store; test restart |
| Two instances still download duplicates | Differing DB/collection/prefix | Compare store configs across instances |
| Remote filter works, local re-emits | Remote and local use different metadata or local is non-persistent | Inspect both filters |
| Filter blocks unfinished file | Marker set before downstream commit | Contract-based recovery/replay |
| `putIfAbsent` always returns old value | Key already exists, possibly from prior run | Inspect state with `get` and check namespace |
| `replace` always returns false | Wrong `oldValue` or key changed | Read current value; handle CAS conflict |
| Duplicates appear after deleting key | Removal made file/event eligible again | Clean up only per procedure |
| Key collision between two flows | Prefix lacks namespace | Design prefixes per environment/flow |
| Re-downloads after SFTP upgrade | Key format/filter behavior changed | Migration plan; test file paths |
| MongoDB outage breaks poller | Metadata I/O requires MongoDB | Health/error channel/retry budget |
| `MongoTemplate` bean ambiguity | Multiple DB beans without qualifiers | `@Qualifier` and database-matched factory |
| App starts but first poll fails | Driver connects/fails lazily on I/O | Readiness probes/timeouts and observability |
| Metadata collection grows unbounded | Missing retention policy | Estimate growth; controlled cleanup |
| Dedup blocks previously failed event | Selector placed marker before business completion | State machine/lease/reconciliation |
| Idempotent advice still invokes handler on duplicate | Missing discard/error config | Check `duplicateMessage` header, `setDiscardChannel` |
| `MetadataStore` registered yet MongoDB inbound still re-reads | Source does not use metadata automatically | Design state/claim in source or selector |
| Business records and metadata mismatch after restore | Inconsistent backup/restore | Replay and idempotency |
| Processor A deletes B's marker | `remove` is not CAS | Never use `remove` as owner release |

Isolation sequence:

~~~text
Inbound file / message
  -> Filter or MetadataStoreSelector
  -> key/value namespace
  -> MongoDbMetadataStore
  -> MongoDatabaseFactory / MongoTemplate
  -> MongoDB collection / driver
  -> MessageChannel / handler
  -> business commit / ACK
~~~

Add logs/metrics separating **metadata write success** from **business handler success**.

## 21. Comprehensive Hands-On Lab

Build an **SFTP/File → Spring Integration → Kafka/DB** pipeline using MongoDB to persist accept-once state.

### Part A — Basic MetadataStore

1. Create database `integration_lab` and configure local/test MongoDB.
2. Define a `ConcurrentMetadataStore` bean using `MongoDbMetadataStore(mongoDatabaseFactory, "integration_metadata")`.
3. Call `get` before writing, call `putIfAbsent` twice, and inspect return values.
4. Call `replace(key, old, new)` with matching and non-matching `oldValue` and compare booleans.
5. Call `remove` on a test key and verify the next `putIfAbsent` succeeds.
6. Create a second store instance pointing to the same factory/collection and verify it sees the same keys.
7. Never reuse a business MongoDB collection directly for storing metadata.

### Part B — File and SFTP Accept-Once

1. Create `FileSystemPersistentAcceptOnceFileListFilter` with a dedicated prefix.
2. Attach it to `FileReadingMessageSource`, configuring a poller and `File` Message consumer.
3. Drop a file into the lab directory and verify it is emitted only once across consecutive polls while unchanged.
4. Restart the process and verify the filter remembers the file via MongoDB.
5. Configure an SFTP remote filter using `SftpPersistentAcceptOnceFileListFilter` with the same store but a distinct prefix.
6. Simulate download failures vs. downstream failures and explain the difference in rollback behavior.
7. Place two identically named files in two directories and inspect keys for your framework version.
8. Run two instances against the shared collection/prefix and verify only one wins each key per filter contract.

### Part C — Idempotent Receiver

1. Create `BusinessEvent(tenantId, eventId, type)` with a stable ID.
2. Build `MetadataStoreSelector` with a key combining environment, tenant, and event ID.
3. Attach `IdempotentReceiverInterceptor`, configure a discard channel, and count blocked duplicates.
4. Send two messages with the same `eventId` but different Spring Message UUIDs; verify the selector still catches the duplicate.
5. Simulate handler failure after the key is stored and discuss the risk of losing retries.
6. Design a `PROCESSING → DONE → RETRY` state machine with leases/owners if business requirements demand it.
7. Simulate a timeout writing metadata when the key may have been created; use `get`/readback before retrying.

### Part D — Production Hardening

1. Design a retention strategy for millions of metadata keys per day.
2. Review MongoDB permissions required for the metadata collection and externalize secrets from code.
3. Select an appropriate write concern and test failover in a test environment.
4. Instrument metrics for `putIfAbsent` wins/losses, CAS conflicts, latency, errors, and business success.
5. Practice a prefix migration on a cloned database and measure duplicates/replays.
6. Design a restore plan when metadata snapshots and business datasets are slightly out of sync.
7. Compare `MongoDbMetadataStore` against `MongoDbMessageStore`, message brokers, and atomic MongoDB claims.

**Self-assessment questions:**

- How does `MetadataStore` differ from `MessageStore`?
- Why can `SimpleMetadataStore` cause duplicates after a restart?
- Which bean types do `MongoDbMetadataStore` constructors accept?
- Does naming a bean `metadataStore` make every adapter use it automatically?
- What does `putIfAbsent` return when inserting succeeds vs. when the key already exists?
- Why does `get + put` have a race across multiple instances?
- What does `replace(key, old, new)` guarantee, and what does it not guarantee?
- Why should `remove(key)` not be used as an owner-checked compare-and-delete?
- How does a persistent accept-once file filter differ from hash-based deduplication?
- How many file filter layers does SFTP inbound have, and what is each responsible for?
- Does a "file seen" marker prove Kafka data has committed?
- If `IdempotentReceiverInterceptor` has no discard configuration, are duplicates necessarily dropped?
- Why must event dedup keys rely on business IDs rather than Spring Message UUIDs?
- Why does registering `MetadataStore` alone not stop `MongoDbMessageSource` from re-polling `NEW` documents?
- When upgrading Spring Integration major versions, what can change in filter keys?
- What risks arise from adding an unplanned TTL index?
- After a MongoDB failover with an ambiguous write result, should you reuse the old key or generate a new key?

## 22. References

- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDB Metadata Store, `MongoDatabaseFactory` wiring, Message Store, and adapters.
- [Spring Integration API — MongoDbMetadataStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/metadata/MongoDbMetadataStore.html): constructors, `get`/`put`/`remove`/`putIfAbsent`/`replace`.
- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): generic key/value state, persistent stores, and `metadataStore` bean lookup.
- [Spring Integration API — ConcurrentMetadataStore](https://docs.spring.io/spring-integration/api/org/springframework/integration/metadata/ConcurrentMetadataStore.html): atomic `putIfAbsent`/`replace` contract.
- [Spring Integration Reference — SFTP Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/sftp/inbound.html): remote/local filters and failure handling.
- [Spring Integration Reference — Remote Persistent File List Filters](https://docs.spring.io/spring-integration/reference/file/remote-persistent-flf.html): key formats, rollback/re-fetch, and shared metadata.
- [Spring Integration API — FileSystemPersistentAcceptOnceFileListFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/file/filters/FileSystemPersistentAcceptOnceFileListFilter.html): constructor accepting `ConcurrentMetadataStore` and prefix.
- [Spring Integration API — SftpPersistentAcceptOnceFileListFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/sftp/filters/SftpPersistentAcceptOnceFileListFilter.html): remote file metadata filter.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): `MetadataStoreSelector`, interceptor, discard, and `duplicateMessage` header.
- [Spring Integration API — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): key/value strategy, `compareValues`, and `accept()`.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): `MongoTemplate`, `MongoDatabaseFactory`, transactions, driver consistency.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) and [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): consistency and durability settings.

## Conclusion

**`MongoDbMetadataStore` is a persistent implementation of `ConcurrentMetadataStore`**, enabling Spring Integration components to store and share key/value metadata across restarts and multiple application instances. The **`putIfAbsent` and `replace`** operations provide atomic per-key updates, making them valuable for File/SFTP/FTP persistent accept-once filters and Idempotent Receivers.

In **SPRING_INTEGRATION_ADAPTERS**, `MetadataStore` holds **coordination state**, not a `MessageChannel`, `MessageStore`, or business database. Proper design requires a shared MongoDB database/collection, stable key namespaces, explicit filter/selector wiring, error/retry policies, and controlled retention. **A "seen" marker never equals completed business processing**: for workflows that cannot lose or duplicate work, you still must design commit/ACK boundaries, lease/claim handling, idempotency, recovery, and cross-system operations.
