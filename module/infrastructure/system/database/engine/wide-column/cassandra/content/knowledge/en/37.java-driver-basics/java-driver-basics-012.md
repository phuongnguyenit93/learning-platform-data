# TypeCodec, GenericType, and Collection/UDT Structures

> **Chapter:** Java Driver Basics  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. The Java driver must convert CQL data types to Java accurately while respecting partition keys, query-driven table design, replication, consistency levels, compaction, repair, and error handling.

## 1. Why Is Type Mapping Part of Correctness?

A Java application reads a Cassandra row:

- Column **tags** is **set<text>**.
- Column **quantities** is **map<text, int>**.
- Column **shipping_address** is a **UDT (User-Defined Type)**.
- Column **created_at** is **timestamp**.

If a developer reads everything as strings, splits by commas manually, or casts a **Map<String, Integer>** to **Map<String, String>**, the app hits type errors, data loss, or corrupt writes. The issue grows sharper with **nested collections**: due to Java's runtime *type erasure*, **Map.class** alone cannot convey key and value types inside.

Java Driver 4.x uses **TypeCodec** to convert between native CQL binary protocol payloads and Java types. **GenericType** preserves parameterized Java types such as **List<String>**, **Set<UUID>**, or **Map<String, List<UUID>>** so the driver selects the right codec.

Lesson objectives:

1. Understand the responsibilities of **TypeCodec**, **GenericType**, and the codec registry.
2. Read and write simple CQL types and collections safely with strong typing.
3. Map **UDTs** from CQL to **UdtValue** and then to application models when needed.
4. Handle nested collections, **frozen** types, **null**, and **UNSET** semantically.
5. Know when to create a **custom codec**, how to register it, and how to test it.
6. Avoid oversized collections/UDTs and prevent read/write failures across distributed Cassandra and Java services.

Examples target the **Java Driver 4.x API** under namespace **com.datastax.oss.driver.api**. Exact dependency versions, Java/JDK support, and cluster settings must match your active driver/server releases.

## 2. Three Layers: CQL Type, Java Type, and Codec

CQL is Cassandra's query language. A CQL column has a type declared in the schema. On the Java side, multiple types can represent corresponding data; codecs bridge the two.

~~~mermaid
flowchart LR
    A["CQL schema: map<text, int>"] --> B["TypeCodec"]
    B --> C["Java: Map<String, Integer>"]
    D["Native protocol binary value"] <--> B
    E["GenericType<Map<String, Integer>>"] --> B
    F["Driver codec registry"] --> B
~~~

### 2.1. What Does TypeCodec Do?

A **TypeCodec<T>** defines the mapping between:

- **CQL DataType**, e.g., **text**, **uuid**, **list<text>**, or **frozen<address>**.
- **Java GenericType<T>**, e.g., **String**, **UUID**, **List<String>**.
- How to **encode** a Java value into bytes for the native protocol.
- How to **decode** bytes from Cassandra into a Java value.
- How to **parse/format** values as CQL literals when needed.

A codec never alters the column's type in the database. If the schema is **map<text, int>**, creating a custom codec **does not turn the column into JSON, a BLOB, or a relational table**; it only changes how Java views/writes values of that CQL type.

### 2.2. What Does GenericType Do?

With **String.class**, Java already retains the basic class metadata. However, **List<String>.class** does not exist: due to type erasure, the runtime class is simply **List.class**. **GenericType** is a *type token* preserving generic arguments.

~~~java
import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<String> textType = GenericType.of(String.class);

GenericType<List<String>> tagsType =
    new GenericType<List<String>>() {};

GenericType<Map<String, List<UUID>>> nestedType =
    new GenericType<Map<String, List<UUID>>>() {};
~~~

Expressions like **new GenericType<...>() {}** create an anonymous subclass retaining concrete type arguments. This is especially helpful for **multi-level generics** or selecting the right codec from a registry with multiple options.

### 2.3. How Does the Codec Registry Select a Codec?

When executing a prepared statement and calling **set/get**, the driver knows the CQL type of each column/bind variable from statement or row metadata. It pairs the **CQL type** with the **requested Java type** to look up a codec in the registry. Most standard types and collections use built-in codecs; custom domain types may require registering a new codec.

~~~text
CQL column + requested Java type
              |
              v
        Codec registry
              |
      Matching codec found?
          /         \
        Yes          No
        |             |
      Encode/       CodecNotFoundException
      decode        or matching mapping error
~~~

**Never rely on post-read casting** to work around a missing codec. A **CodecNotFoundException** usually signals that the driver cannot convert between the **CQL DataType** and the requested **Java GenericType**. Inspect the schema, Java type, and registry rather than casting results.

## 3. Common Mappings Between CQL and Java

| CQL | Typical Java Type in Driver 4.x | Notes |
|---|---|---|
| **text, varchar, ascii** | **String** | Character-set constraints still follow the CQL type |
| **boolean** | **Boolean** | Nullable fields should use wrappers over primitives to distinguish null |
| **tinyint, smallint, int, bigint** | **Byte, Short, Integer, Long** | Never assume numeric types automatically widen as desired |
| **float, double** | **Float, Double** | Watch floating-point representation error |
| **decimal** | **BigDecimal** | Ideal for currency/decimals with business rounding rules |
| **varint** | **BigInteger** | Never cast to Long if values can exceed 64-bit range |
| **uuid, timeuuid** | **UUID** | `timeuuid` carries time-based semantics |
| **timestamp** | **Instant** | Stored at millisecond precision; standardize on UTC |
| **date** | **LocalDate** | Calendar date without timezone or time of day |
| **time** | **LocalTime** | Time of day without calendar date |
| **blob** | **ByteBuffer** | Manage buffer positions on read/write; avoid unbounded objects |
| **list<text>** | **List<String>** | Ordered collection |
| **set<uuid>** | **Set<UUID>** | Do not rely on business ordering |
| **map<text, int>** | **Map<String, Integer>** | Requires both key and value types |
| **UDT** | **UdtValue** | Optional custom codec can map directly to a domain class |

This table lists common mappings, not every supported CQL/Java codec. When a column is **null**, getters return a null reference or require checking **row.isNull(...)** depending on context. Never turn null into the string **"null"** when business logic distinguishes both states.

### 3.1. Do Not Confuse Temporal Types

- **timestamp** represents an instant; Java typically uses **Instant**, keeping consistent UTC rules.
- **date** represents only a calendar date; Java uses **LocalDate** without attaching a timezone.
- **time** is time of day; Java uses **LocalTime** without attaching an arbitrary date.
- When Java uses nanosecond-precision **Instant**, writing to CQL `timestamp` drops sub-millisecond digits; verify your application's precision requirements.

Example:

~~~java
import java.time.Instant;
import java.time.LocalDate;

Instant happenedAt = Instant.parse("2026-11-21T03:05:00Z");
LocalDate eventDay = LocalDate.of(2026, 11, 21);
~~~

**Partition routing is independent of codecs**, yet picking the wrong type or miscomputing **event_day** writes the event into a different partition, causing partition-key queries to miss the data.

## 4. Example Schema: Collections and UDTs in a Wide-Column Table

For practice, model a table serving the query: **"fetch the latest orders for a customer on a given day"**. Unbounded time-series growth is bucketed by **day**, rather than stuffing every order into an infinitely growing partition.

~~~sql
-- Adjust dc1 and RF to match your test environment topology.
-- Example RF = 3 needs enough replicas to test LOCAL_QUORUM like production.
CREATE KEYSPACE IF NOT EXISTS shop_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TYPE IF NOT EXISTS shop_lab.address (
    line1 text,
    city text,
    postal_code text
);

CREATE TABLE IF NOT EXISTS shop_lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    tags set<text>,
    quantities map<text, int>,
    notes list<text>,
    shipping_address frozen<address>,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

### 4.1. Role of Each Component

- **(customer_id, order_day)** is the **composite partition key**: binding both lets the driver compute the routing key/token and pick an optimal coordinator when metadata/driver support it.
- **created_at, order_id** are **clustering columns**: disambiguate and sort rows within the partition.
- **tags** is a bounded **set<text>**, such as `"priority"` or `"mobile"`.
- **quantities** is a **map<text, int>**, mapping SKU codes to counts.
- **notes** is a **list<text>**, suitable only for small, bounded item counts.
- **shipping_address** is **frozen<address>**: the UDT is treated as a single atomic value on writes/updates.

**Never use a UDT or collection to store a customer's entire history**. If data grows unboundedly or requires paginating individual items, model them as rows with proper partition/clustering keys. Oversized collections create heavy mutations, emit tombstones on updates/deletes, and burden compaction/repair.

### 4.2. Sample CQL Row to Visualize Values

~~~sql
INSERT INTO shop_lab.orders_by_customer_day (
    customer_id, order_day, created_at, order_id,
    tags, quantities, notes, shipping_address
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T03:05:00Z',
    22222222-2222-4222-8222-222222222222,
    {'priority', 'web'},
    {'sku-001': 2, 'sku-002': 1},
    ['paid', 'packed'],
    {line1: '123 Example St', city: 'Hanoi', postal_code: '100000'}
);
~~~

This is fixture data only. Addresses, IDs, and strings are illustrative, not real personal data. In Java apps, prefer **PreparedStatement + bind** instead of concatenating user fields into CQL strings.

## 5. Reading and Writing Collections with Java Driver 4.x

Convenience getters/setters support **List, Set, and Map** directly when element types are simple.

### 5.1. Reading Collections

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import com.datastax.oss.driver.api.core.cql.Row;

void inspectRow(Row row) {
    Set<String> tags =
        row.getSet("tags", String.class);

    Map<String, Integer> quantities =
        row.getMap("quantities", String.class, Integer.class);

    List<String> notes =
        row.getList("notes", String.class);

    if (tags != null && tags.contains("priority")) {
        System.out.println("Order has priority tag");
    }

    if (quantities != null) {
        System.out.println("Number of distinct SKUs: " +
                           quantities.size());
    }
}
~~~

**getSet/getMap/getList** pass element types explicitly to the driver. Avoid **row.getObject("tags")** with unchecked casts when strong generic safety matters. If you pass mismatched map value types—such as calling **getMap("quantities", String.class, String.class)** for **map<text,int>**—no matching codec exists.

**Returned values can be null** when the column is unset in CQL. If business logic expects empty collections, normalize explicitly at the service layer; never mix **null** and **empty set/map/list** unconsciously.

### 5.2. Writing Collections with BoundStatement

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

BoundStatement bindCollections(PreparedStatement insert) {
    BoundStatement statement = insert.bind()
        .setSet("tags", Set.of("priority", "web"), String.class)
        .setMap("quantities",
                Map.of("sku-001", 2, "sku-002", 1),
                String.class, Integer.class)
        .setList("notes", List.of("paid", "packed"), String.class);

    return statement;
}
~~~

**Note:** this snippet assumes the prepared `INSERT` uses **named bind markers** matching **tags**, **quantities**, and **notes**. When using positional **?** markers, Driver 4.x often binds by column-derived variable names, yet names can collide or be non-obvious in complex queries. In the complete example below, we use **positional indices** for consistency.

Driver 4.x makes statements **immutable**: every **set...** method returns a **new `BoundStatement`** that must be **reassigned or chained**. Ignoring the return value sends the old unbound/previous statement.

### 5.3. Mutating Collections Can Create Tombstones

For non-**frozen** collections, partial updates are possible depending on collection type:

~~~sql
UPDATE shop_lab.orders_by_customer_day
SET quantities['sku-001'] = 3
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T03:05:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
~~~

Updating or deleting elements can generate cells/tombstones processed during reads and compaction. **Especially with lists**, index mutations or prepends carry distinct costs compared to small appends; never treat a list like an unbounded queue, especially under concurrent client updates.

## 6. UDTs: Defined in Schema, Used as UdtValue in Java

A **UDT (User-Defined Type)** groups related fields into a schema-typed CQL structure, such as **address(line1, city, postal_code)**. UDTs are not schemaless JSON: field names and types are enforced by **CREATE TYPE** and tracked in keyspace metadata.

### 6.1. Retrieving UDT Metadata

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

UserDefinedType addressType = session.getMetadata()
    .getKeyspace(CqlIdentifier.fromCql("shop_lab"))
    .flatMap(ks -> ks.getUserDefinedType(
        CqlIdentifier.fromCql("address")))
    .orElseThrow(() ->
        new IllegalStateException("UDT shop_lab.address does not exist"));
~~~

Here **session** is an initialized **CqlSession**. Before reading metadata, ensure the schema exists and all nodes have reached schema agreement. Creating a UDT and immediately preparing or querying metadata before schema propagation can fail.

### 6.2. Creating and Binding UdtValue

~~~java
import com.datastax.oss.driver.api.core.data.UdtValue;

UdtValue address = addressType.newValue()
    .setString("line1", "123 Example St")
    .setString("city", "Hanoi")
    .setString("postal_code", "100000");

// Assumes prepared statement has shipping_address at index 7.
BoundStatement statement = preparedInsert.bind()
    .setUdtValue(7, address);
~~~

**UdtValue** stores typed fields matching the UDT definition. You do not serialize it manually to JSON for a **frozen<address>** column: the driver uses the matching UDT codec to encode it.

### 6.3. Reading UdtValue and Checking for Null

~~~java
UdtValue shipping = row.getUdtValue("shipping_address");

if (shipping != null) {
    String city = shipping.getString("city");
    String postalCode = shipping.getString("postal_code");
    System.out.println("Shipping city: " + city);
}
~~~

In real apps, addresses may be sensitive data; printing the city simply illustrates field reads. Never log raw `UdtValue`s, addresses, or PII in operational logs without legitimate need and authorization.

### 6.4. Frozen UDT vs. Non-Frozen UDT

| Structure | Semantics to Note | When Appropriate |
|---|---|---|
| **frozen<address>** | Treated as **a single atomic value** on writes/updates; replaces the whole UDT | A small cohesive structure tightly bound to a row |
| **address** (non-frozen, if release supports needed semantics) | Allows individual field updates depending on structure/version | When partial field updates are intentionally needed |
| **text JSON** | No Cassandra UDT typing; app parses/validates itself | Only when unstructured payloads are truly needed and trade-offs accepted |

UDTs do not solve **large partition** problems: large UDTs repeated across many rows or mutated frequently still amplify mutation, SSTable, compaction, and repair load.

## 7. GenericType for Nested Collections

Java's generic type erasure prevents **Map.class** from expressing **String → List<UUID>**. For nested structures, use **GenericType** to specify the exact target type.

CQL can model a map holding frozen lists:

~~~sql
-- Practice on a separate table or add a column in a lab environment.
CREATE TABLE IF NOT EXISTS shop_lab.events_by_group (
    tenant_id uuid,
    bucket_day date,
    group_name text,
    ids_by_kind map<text, frozen<list<uuid>>>,
    PRIMARY KEY ((tenant_id, bucket_day), group_name)
);
~~~

**frozen<list<uuid>>** as a map value encodes each nested list as a single immutable value; confirm syntax compatibility with your Cassandra version. Nested payloads still require **strict bounds on element counts and byte sizes**.

### 7.1. Reading with a Type Token

~~~java
import java.util.List;
import java.util.Map;
import java.util.UUID;
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<Map<String, List<UUID>>> nestedType =
    new GenericType<Map<String, List<UUID>>>() {};

Map<String, List<UUID>> ids =
    row.get("ids_by_kind", nestedType);
~~~

Here `GenericType` tells the registry not just **Map**, but also **key = String** and **value = List<UUID>**. Never cast to **Map<String, List<String>>** or fall back to raw **Map**.

### 7.2. Binding Nested Values

~~~java
Map<String, List<UUID>> idsByKind = Map.of(
    "order", List.of(UUID.fromString(
        "22222222-2222-4222-8222-222222222222")));

BoundStatement bound = prepared.bind()
    .set(3, idsByKind, nestedType);
~~~

This assumes bind index **3** is **ids_by_kind** and all remaining indices are bound before execution. **Indices in `BoundStatement` are 0-based**; if schema or parameter order changes, misbinding causes type mismatches or corrupt data.

In production apps, use prepared statements matching primary keys and build test fixtures for every nested type. If partial queries inside nested collections aren't needed, simpler structures are often easier to maintain.

## 8. Complete Example: INSERT and SELECT with Collections + UDT

The Java Driver 4.x example below shows the full lifecycle: opening a session, fetching UDT metadata, preparing statements, binding typed values, writing, and reading back. Intended for the **lab environment** with the Section 4 schema already created.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

public class OrderCollectionsUdtDemo {
    public static void main(String[] args) {
        UUID customerId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID orderId = UUID.fromString(
            "22222222-2222-4222-8222-222222222222");
        LocalDate orderDay = LocalDate.of(2026, 11, 21);
        Instant createdAt = Instant.parse("2026-11-21T03:05:00Z");

        // Adjust contact point, DC, and security for your lab environment.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            UserDefinedType addressType = session.getMetadata()
                .getKeyspace(CqlIdentifier.fromCql("shop_lab"))
                .flatMap(k -> k.getUserDefinedType(
                    CqlIdentifier.fromCql("address")))
                .orElseThrow();

            UdtValue address = addressType.newValue()
                .setString("line1", "123 Example St")
                .setString("city", "Hanoi")
                .setString("postal_code", "100000");

            PreparedStatement insert = session.prepare(
                "INSERT INTO shop_lab.orders_by_customer_day " +
                "(customer_id, order_day, created_at, order_id, " +
                "tags, quantities, notes, shipping_address) " +
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind()
                .setUuid(0, customerId)
                .setLocalDate(1, orderDay)
                .setInstant(2, createdAt)
                .setUuid(3, orderId)
                .setSet(4, Set.of("priority", "web"), String.class)
                .setMap(5, Map.of("sku-001", 2),
                        String.class, Integer.class)
                .setList(6, List.of("paid"), String.class)
                .setUdtValue(7, address)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);

            PreparedStatement select = session.prepare(
                "SELECT tags, quantities, notes, shipping_address " +
                "FROM shop_lab.orders_by_customer_day " +
                "WHERE customer_id = ? AND order_day = ? " +
                "AND created_at = ? AND order_id = ?");

            Row row = session.execute(
                select.bind(customerId, orderDay, createdAt, orderId)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            if (row == null) {
                throw new IllegalStateException("Order not found");
            }

            Set<String> tags = row.getSet("tags", String.class);
            Map<String, Integer> quantities =
                row.getMap("quantities", String.class, Integer.class);
            UdtValue actualAddress =
                row.getUdtValue("shipping_address");

            if (tags == null || !tags.contains("priority")
                    || quantities == null
                    || !Integer.valueOf(2)
                        .equals(quantities.get("sku-001"))
                    || actualAddress == null
                    || !"Hanoi".equals(
                        actualAddress.getString("city"))) {
                throw new IllegalStateException(
                    "Collection/UDT mapping did not match fixture");
            }

            System.out.println(
                "PASS: mapped collection and UDT correctly");
        }
    }
}
~~~

### 8.1. Prerequisites to Run the Example

- **shop_lab**, **address**, and the table exist with schema agreement.
- Contact point targets the lab Cassandra node and **dc1** matches the actual datacenter name.
- With RF = 3 in the local DC, **LOCAL_QUORUM** requires enough responding replicas (typically 2/3); a single-node lab will not satisfy that production setup. Adjust lab RF/CL and note the difference.
- **Set.of, Map.of, List.of** require Java 9+; use a JDK-compatible driver dependency.
- TLS/auth are omitted to keep focus on `TypeCodec`. Real systems must enable authentication and encryption—never disable security to run samples.
- **PreparedStatement** and **CqlSession** should be cached/reused in long-lived applications; this example opens one in `main` for standalone clarity.
- UUIDs and addresses are fixtures; real retries must preserve `orderId` rather than generating a fresh ID per attempt.
- **.one()** returns null if no row exists, so always check presence before calling getters.

## 9. Custom TypeCodec: When Java Types Are Domain Objects

The driver ships codecs for **String, UUID, Instant, collections, UdtValue**, and many primitives. If an app prefers a custom Java type like **Priority** instead of `String`, you can write a custom codec mapping CQL **text** to the enum.

**Only build a custom codec when the mapping is genuinely used broadly.** If you only convert `UdtValue` to a DTO in one service, an explicit mapper function is simpler and carries less session-wide risk than a global codec.

### 9.1. Enum TypeCodec Example

~~~java
import java.nio.ByteBuffer;

import com.datastax.oss.driver.api.core.ProtocolVersion;
import com.datastax.oss.driver.api.core.type.DataType;
import com.datastax.oss.driver.api.core.type.DataTypes;
import com.datastax.oss.driver.api.core.type.codec.TypeCodec;
import com.datastax.oss.driver.api.core.type.codec.TypeCodecs;
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

enum Priority {
    NORMAL, URGENT
}

final class PriorityCodec implements TypeCodec<Priority> {
    private static final GenericType<Priority> JAVA_TYPE =
        GenericType.of(Priority.class);

    @Override
    public GenericType<Priority> getJavaType() {
        return JAVA_TYPE;
    }

    @Override
    public DataType getCqlType() {
        return DataTypes.TEXT;
    }

    @Override
    public ByteBuffer encode(
            Priority value, ProtocolVersion protocolVersion) {
        return TypeCodecs.TEXT.encode(
            value == null ? null : value.name(),
            protocolVersion);
    }

    @Override
    public Priority decode(
            ByteBuffer bytes, ProtocolVersion protocolVersion) {
        String name = TypeCodecs.TEXT.decode(bytes, protocolVersion);
        return name == null ? null : Priority.valueOf(name);
    }

    @Override
    public String format(Priority value) {
        return TypeCodecs.TEXT.format(
            value == null ? null : value.name());
    }

    @Override
    public Priority parse(String literal) {
        String name = TypeCodecs.TEXT.parse(literal);
        return name == null ? null : Priority.valueOf(name);
    }
}
~~~

This codec **delegates string and CQL literal encoding/decoding** to **TypeCodecs.TEXT** and converts between `String` and the enum. Reusing the built-in codec handles protocol framing and quoting cleanly instead of hand-rolling charsets, `ByteBuffer`s, or string escaping. All enum values must stay compatible with existing data; **Priority.valueOf** will throw on unknown values like **"CRITICAL"** if the enum lacks them.

Any custom codec handling real data must be tested against:

- **null**, empty strings, Unicode, and valid enum values.
- Invalid data or newer enum values written by another service.
- All protocol versions supported by driver/server.
- Never mutating input **ByteBuffer**s or sharing mutable buffers improperly.
- Encode/decode round-trips, format/parse round-trips, and clear mapping errors.
- Thread safety of the codec since the session/driver invokes it concurrently.
- Backward compatibility during rolling deployments of multiple app versions.

### 9.2. Registering a Codec on the Session

Driver 4.x builder APIs support codec registration:

~~~java
try (CqlSession session = CqlSession.builder()
        .addContactPoint(
            new java.net.InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc1")
        .addTypeCodecs(new PriorityCodec())
        .build()) {

    // Session uses a registry containing PriorityCodec.
    // Requires a matching CQL text column to bind/get the enum.
}
~~~

Session registration governs codec selection whenever the **CQL DataType + Java GenericType pair** matches. Multiple codecs can share the same CQL type with different Java types, such as `String` and `Priority`. Never register duplicate codecs for the exact same pair expecting the driver to guess when values are null or generics are erased.

### 9.3. Using a Custom Codec Explicitly

Assuming a **priority text** column in a test table, select the Java type using `GenericType`:

~~~java
GenericType<Priority> priorityType =
    GenericType.of(Priority.class);

// Prepared INSERT/UPDATE defines a 'priority' marker.
BoundStatement bound = prepared.bind()
    .set("priority", Priority.URGENT, priorityType);

// Row read from SELECT includes text column 'priority'.
Priority value = row.get("priority", priorityType);
~~~

This snippet illustrates **type-driven codec selection**; it requires a prepared statement with matching markers, schema table, and full partition key bound prior to execution. In real apps, if a field appears in only one place, **row.getString** followed by domain parsing is often simpler.

## 10. TypeCodec for UDTs: Choosing Between a Mapper and a Custom Codec

There are two standard ways to bring an **address UDT** into your Java domain model.

### 10.1. Explicit Mapper at the Service Layer

Simple domain class example:

~~~java
record Address(String line1, String city, String postalCode) {}

static Address toAddress(UdtValue value) {
    if (value == null) {
        return null;
    }
    return new Address(
        value.getString("line1"),
        value.getString("city"),
        value.getString("postal_code"));
}

static UdtValue toUdt(
        Address address, UserDefinedType type) {
    if (address == null) {
        return null;
    }
    return type.newValue()
        .setString("line1", address.line1())
        .setString("city", address.city())
        .setString("postal_code", address.postalCode());
}
~~~

**record** requires Java 16+. On earlier JDKs, use an immutable class. This assumes **UdtValue** and **UserDefinedType** imports as in Section 6.

Pros:

- Easy to unit-test independently and handle missing/null fields explicitly.
- Keeps the codec registry untouched.
- Can enforce business validation such as address length or postal code format.

Cons: requires calling the mapper at read/write sites, so share the helper cleanly if multiple services use the same structure.

### 10.2. Custom UDT Codec for Domain Types

You can write a codec converting **UdtValue ↔ Address** using dedicated codec utilities or delegating to the base UDT codec, depending on driver APIs. This requires fetching **UserDefinedType metadata** for the exact keyspace/schema, registering the codec for that CQL type and Java `GenericType`, and calling **row.get(..., GenericType.of(Address.class))** or the matching setter.

With custom UDT codecs, watch out for:

1. **Schema evolution:** adding/removing/renaming fields alters mappings. Rigid codecs can break on mixed-version nodes or right after schema changes.
2. **UDT identifiers:** identically named UDTs in two keyspaces can have different definitions. Never assume every UDT named **address** is identical.
3. **Frozen/non-frozen:** handle whole-value vs. field-level update semantics at the CQL layer, not just in the codec.
4. **Null fields:** UDT fields can be null; domain models need explicit rules.
5. **Thread safety:** codecs are shared across requests; never store per-request mutable state in a shared codec instance.
6. **Server/driver compatibility:** codecs do not change the wire protocol or make incompatible schemas compatible.

For newcomers, **`UdtValue` + explicit mapper** is usually the best starting point. Upgrade to a custom codec only for measurable benefit and with round-trip/schema-evolution tests in place.

## 11. Null, UNSET, Empty Collections, and Data Impact

Four frequently confused states:

| Representation | Common Meaning | Caution |
|---|---|---|
| **null** | No value; on writes under CQL semantics, may emit a **tombstone** | Never use as "keep existing" when you want to skip updating |
| **UNSET** in bind | For supported statements, marker skips updating that column | Never use on primary keys or positions disallowed by the server |
| **Empty collection** | Collection value with zero elements per type semantics | Distinct from populated collections; read/write details depend on frozen vs. non-frozen |
| **Null collection** | Column has no value | Never treat as an empty collection if business logic separates them |

The Java driver provides **setToNull** and **unset** on supported statements. Example on an **UPDATE** with named markers:

~~~java
BoundStatement keepTags = preparedUpdate.bind()
    .unset("tags");

BoundStatement clearTags = preparedUpdate.bind()
    .setToNull("tags");
~~~

These two statements are **not equivalent**: `UNSET` tells the server to ignore the marker and leave the column untouched; `null` acts as a deletion. Valid `UNSET` syntax and positions depend on statement type and version—test against a lab table first.

Crucial safety reminder: **`BoundStatement` is immutable**. Writing:

~~~java
BoundStatement original = preparedUpdate.bind();
original.setToNull("tags");  // Discards return value: original is unchanged!
~~~

executes `original` with the marker still unbound. Write:

~~~java
BoundStatement corrected =
    original.setToNull("tags");
~~~

When implementing a PATCH API in Java, define all three intents separately: **field omitted (keep)**, **explicit null (clear)**, and **empty value (valid empty collection)**. Mixing them accidentally wipes data and emits unwanted tombstones.

## 12. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Check |
|---|---|---|
| **CodecNotFoundException** | CQL type mismatches requested Java type; missing custom codec | Inspect schema, `GenericType`, column/marker, and codec registry |
| **ClassCastException** | Casting raw collections or wrong generics | Use typed getters or exact `GenericType` |
| **InvalidTypeException** or bind error | Marker passed wrong type for schema; wrong UDT field name/type | Compare `PreparedStatement` metadata against `CREATE TABLE`/`TYPE` |
| **NullPointerException** after `getUdtValue` | UDT column is null or row absent | Check `row == null`, `row.isNull`, and `UdtValue == null` |
| **Timestamp** values off | UTC/timezone confusion or expecting nanosecond precision | Use `Instant`, boundary date/time fixtures, verify millis |
| Record not found | Miscomputed composite partition key or bucket | Check `customer_id + order_day`, routing key, and bound values |
| Update misses a field | Discarded new statement returned by setter | Reassign `BoundStatement` after every `set`/`unset` |
| **UDT codec** fails after schema migration | Field/UDT metadata changed; cache/driver stale | Check schema agreement, type identifiers, and mappers |
| Memory/latency grows due to collections | Oversized collections/mutations or repeated updates/deletes | Cap element counts, measure partition size/tombstones, model as rows |
| Sensitive data leaks in logs | Logging `UdtValue`/`BoundStatement`, payloads, or full queries | Redact at source, log query shape only, never log PII |

### 12.1. Procedure for Handling `CodecNotFoundException`

1. **Record the exact CQL type** of the column or bind marker: e.g., **map<text, int>**.
2. **Record the Java type requested by code**: e.g., **Map<String, String>**, which mismatches the column above.
3. Verify the **right getter/setter** is used, especially for nested generics.
4. For custom domain classes, confirm the **codec is registered on the right `CqlSession`** with matching `DataType` and `GenericType`.
5. Check **schema agreement** if the error follows `CREATE`/`ALTER TYPE` or a rolling upgrade.
6. Add **round-trip** conversion tests against real schema and boundary values.

Never "fix" mapping errors by coercing everything to **text** or adding **ALLOW FILTERING**. A type-mapping bug has nothing to do with scanning multiple partitions.

### 12.2. Logging Enough to Diagnose Without Leaking Data

For codec errors, log **operation name**, keyspace/table, **column name and type**, expected Java type, codec class, driver/server versions, and exception class. Never log passwords, customer addresses, tokens, real collection contents, or user UDTs.

## 13. How Does TypeCodec Relate to Replication, Consistency, and Performance?

`TypeCodec` runs primarily at the **client/protocol boundary**, translating between Java and CQL. Once encoded, the request still routes by **partition key**; the coordinator selects replicas per topology, replication strategy, and request CL.

~~~mermaid
flowchart LR
    A["Java Domain + GenericType"] --> B["TypeCodec encode"]
    B --> C["BoundStatement + partition key"]
    C --> D["Coordinator and token-aware routing"]
    D --> E["Replicas per RF + CL"]
    E --> F["Commitlog / memtable / SSTable"]
    F --> G["Compaction / repair"]
    G --> H["Read returns data → TypeCodec decode"]
~~~

Consequences:

- **The right codec cannot save a query missing its partition key.** Design tables around access patterns so queries know which partition to read.
- **Codecs do not change consistency levels.** Writing at **LOCAL_QUORUM** enforces different replica responses from **ONE**, while returned Java types still use the same codecs.
- **Codecs do not lift mutation/batch/partition limits.** Oversized maps/UDTs still stress buffers, networks, and I/O even when encoded accurately.
- **Codecs do not replace repair.** Repair synchronizes replicas; the app must ensure it does not write bad types, wrong partitions, or wrong TTLs in the first place.
- **Driver retries can resend requests.** When updating collections or creating rows, design idempotency using stable `orderId`/`eventId` values instead of minting new UUIDs on every retry.
- **Custom codecs cost CPU/GC.** Allocating excessive temporary `String`/`ByteBuffer` objects or deep-copying large collections per request raises latency. Measure allocations, p95/p99, and concurrent request counts before tuning.

### 13.1. Collection Strategy Fitting the Wide-Column Model

A **tags set<text>** with a handful of labels makes sense. Conversely, tens of thousands of event IDs stuffed into a per-customer map grows without bound. Better alternative:

~~~sql
CREATE TABLE IF NOT EXISTS shop_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    category text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

Each event is a row, paginated by clustering key; still monitor daily partition sizes and hot-tenant rates. When reading across multiple days, query bounded daily buckets and merge results cleanly.

## 14. Testing Data Types Properly, Not Just Connectivity

A test suite for `TypeCodec`/`GenericType` should cover three levels:

### Level A — Codec/Mapping Unit Tests

- Java → encode → decode → Java for typical values.
- Null, empty, Unicode, special characters, integer min/max, `BigDecimal` scales, and temporal precision.
- Empty collections, collections up to application caps, and nested generics.
- UDTs with null fields, plus added/removed fields simulating schema migrations.
- Unknown enum values and invalid payloads; clear errors without leaking data.
- Concurrent multi-threaded usage of shared codec instances (when registered on a session).

### Level B — Cassandra Lab Integration Tests

- Create CQL schema and UDTs; wait for schema agreement.
- Prepared `INSERT`/`SELECT` with full composite partition keys and clustering columns.
- Bind/get `list`/`set`/`map`/UDTs, asserting **both exact types and values**, not merely absence of exceptions.
- Test **`setToNull`** and **`unset`** on `UPDATE`s, verifying data semantics.
- Inspect rows with TTLs/`DELETE`s and collection updates to catch tombstone behavior.
- Test codecs against differing keyspace/UDT names or schemas to expose hardcoded assumptions.

### Level C — Load, Rolling Upgrades, and Distributed Failures

- Measure p95/p99, allocation rates, GC, and driver CPU when serializing collections/UDTs under load.
- Test page sizes, concurrency, and backpressure on multi-row queries.
- Test timeouts/retries against replica failures while keeping idempotent event IDs.
- Verify driver/server compatibility, TLS/auth, and schema agreement during `ALTER TYPE`.
- Monitor compaction, repair, and partition sizes under frequent collection mutations.
- Validate backup/restore alongside UDT schemas, since file snapshots alone do not capture Java domain mapper expectations.

## 15. Practice Exercises

### Exercise 1 — Choose the Right Java Types

Given schema:

~~~sql
CREATE TABLE shop_lab.codec_exercise (
    id uuid PRIMARY KEY,
    labels set<text>,
    scores map<text, int>,
    dates list<date>
);
~~~

Write the matching Java types for the three collection columns.

**Suggested answer:** **Set<String>**, **Map<String, Integer>**, **List<LocalDate>**. Avoid raw `Map`, and use `LocalDate` for `dates` since CQL `date` carries no time of day.

### Exercise 2 — Why Is GenericType Needed?

A column is declared **map<text, frozen<list<uuid>>>**. A developer passes **Map.class** and casts to **Map<String, List<UUID>>**.

**Question:** What goes wrong when generic type info is lost? How should it be read?

**Suggested answer:**

~~~java
GenericType<Map<String, List<UUID>>> type =
    new GenericType<Map<String, List<UUID>>>() {};
Map<String, List<UUID>> result =
    row.get("ids_by_kind", type);
~~~

The codec registry needs full type information; casting a raw `Map` bypasses compile-time deep type checking and fails at runtime when inspecting elements.

### Exercise 3 — Null UDT Value

A table has **shipping_address frozen<address>**, and one row has no address. Code calls:

~~~java
String city = row.getUdtValue("shipping_address")
                 .getString("city");
~~~

**Question:** What error can occur? How do you fix it?

**Suggested answer:** **NullPointerException** when `UdtValue` is null. Check row existence and UDT nullability before reading fields; distinguish "no address" from an empty city string.

### Exercise 4 — Immutable BoundStatement

~~~java
BoundStatement b = update.bind();
b.setSet("tags", Set.of("vip"), String.class);
session.execute(b);
~~~

**Question:** Why might the request still fail to bind `tags`?

**Suggested answer:** The setter returns a new statement; the code discarded the return value. Use **`b = b.setSet(...)`** or chain before `execute`.

### Exercise 5 — Custom Enum Codec Encounters New Data

A custom codec maps **text** to enum **NORMAL, URGENT** via **Priority.valueOf**. Another service writes **"CRITICAL"**.

**Question:** What happens? How should compatible rollouts be designed?

**Suggested answer:** Decoding fails because the enum constant does not exist. For multi-version rollouts, plan handling for unknown values, deploy readers before writers, test old/new data versions together, and govern the codec registry.

### Exercise 6 — Do Oversized Collections Concern TypeCodec?

An app successfully encodes a **map<text, text>** with 100,000 entries and writes it into one row per customer.

**Question:** Does a working codec guarantee healthy queries and nodes?

**Suggested answer:** No. Mutations, collections, and partitions grow huge, straining CPU/network/RAM and generating tombstones on updates; bound collection sizes, model history as rows per partition/bucket, and monitor compaction/repair.

### Exercise 7 — Wrong Bucket Causes "Phantom" Data Loss

A Java service writes **order_day** in UTC, while the read API computes `LocalDate` in a local timezone. An event at 23:30 UTC gets queried under the next calendar day.

**Question:** Is `TypeCodec` at fault?

**Suggested answer:** `TypeCodec` works fine; the bug is inconsistent **partition key bucket calculation**. Standardize date/bucket calculation across writes and reads and test midnight boundaries.

## 16. Checklist When Adopting Type Mapping in Java Apps

- [ ] CQL schema and Java mappings are reviewed together, including **UDTs and nested collections**.
- [ ] **GenericType** tokens are used for complex generics; never rely on raw casts.
- [ ] Typed getters/setters such as **getMap/setMap, getList/setList, getUdtValue/setUdtValue** are used.
- [ ] Prepared statements bind full partition keys in exact order/markers with routing metadata.
- [ ] **BoundStatement immutability** is respected by retaining setter return values.
- [ ] Semantics for **null, UNSET, and empty collections** are explicitly defined.
- [ ] UDTs are retrieved from metadata in the exact keyspace after schema agreement, handling null fields.
- [ ] Custom `TypeCodec`s implement encode/decode/parse/format and are tested across protocols and invalid inputs.
- [ ] Raw `UdtValue`s, secrets, or sensitive payloads are never logged.
- [ ] Collections/UDTs stay small and bounded; unbounded growth is modeled as multiple rows per access pattern.
- [ ] Test fixtures cover partition keys, token distribution, TTL/`DELETE`, and temporal boundary values.
- [ ] Consistency levels, retries/idempotency, driver/server compatibility, and load performance are tested.
- [ ] Backups, compaction, and repair are accounted for in operations when data structures evolve.

## 17. Summary

**TypeCodec** handles **CQL DataType ↔ Java value** conversion, while **GenericType** gives the driver exact Java types—including nested generics lost to Java type erasure. **Collections** fit small, bounded value sets on a row; **UDTs** express schema-enforced structures accessed via **UdtValue** or mapped to domain objects with mappers/custom codecs.

In Cassandra, accurate mapping is only part of correctness. Partition keys must be bound consistently, tables must be query-driven, consistency levels must match replication, and collections/UDTs must stay small enough not to overload mutations, compaction, or repair. With the Java driver, the safe path is **typed prepared/bound statements, explicit null/UNSET checks, bounded payloads, round-trip testing, and distributed behavior verification** prior to production.
