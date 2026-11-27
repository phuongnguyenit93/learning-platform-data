# tuple, UDT, frozen, and Storage Semantics in Apache Cassandra

When modeling **wide-column** data in Apache Cassandra, not every group of values deserves its own table, nor should everything be crammed into one giant "object." CQL provides **`tuple`** to store a group of elements **with fixed positions and types**, **UDT** (*user-defined type*) to store a group of fields **with explicit names and types**, and the **`frozen<...>`** keyword to instruct Cassandra to treat an entire composite value **as a single unit** rather than independently updatable fields/elements.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The module's goal is to understand Apache Cassandra's distributed architecture and wide-column model, choose partition keys, design query-driven tables, configure read/write consistency levels, practice CQL, and handle replication, compaction, repair, error handling, and Java connectivity. Within that context, **tuple/UDT/frozen govern semantics and the unit of mutation**, while **partition keys and clustering columns** must still be designed around queries.

## 1. Selection Guide Table

| Structure | Components | CQL Declaration | Can Individual Components Be Updated? | Best Suited For |
|---|---|---|---|---|
| **Tuple** | Positional, typed, **unnamed fields** | `tuple<double, double>` | **No**: tuples are always treated as frozen | A coordinate pair, a small pair with obvious positional meaning |
| **Non-frozen UDT** | **Named fields**, typed | `postal_address` | **Yes**, for UDTs and CQL operations supported by the version | A current address needing independent single-field edits |
| **Frozen UDT** | Named fields, typed | `frozen<postal_address>` | **No**: replace the entire value | A snapshot of shipping address attached to an order |
| **Non-frozen collection** | List/set/map with matching element types | `set<text>`, `map<text,text>` | Supports certain per-element updates | Small, bounded groups of elements |
| **Frozen collection** | List/set/map packed as a single value | `frozen<map<text,text>>` | **No**: replace the entire value | Small configuration versioned as a snapshot |
| **Multi-row table** | Each entity has its own primary key | `CREATE TABLE ... PRIMARY KEY (...)` | Can update/query row by row | Large datasets growing over time, needing pagination or independent lookups |

**Do not interpret "frozen" as "the data can never be updated."** A `frozen<postal_address>` column **can still be replaced with a new value**. What is restricted is **updating a single nested field inside** the frozen value. The word `frozen` describes **how Cassandra treats the value as a monolithic unit**, not an application-level "immutable" guarantee.

## 2. Tuple: Fixed Structure by Positional Order

### 2.1. What Is a Tuple?

`tuple<T1, T2, ...>` represents a **positional** group of fields. Each position has a defined CQL type; the types **may differ**.

~~~cql
CREATE TABLE geo_samples_by_id (
    sample_id uuid PRIMARY KEY,
    coordinates tuple<double, double>,
    quality tuple<int, text>
);

INSERT INTO geo_samples_by_id (
    sample_id, coordinates, quality
) VALUES (
    11111111-1111-4111-8111-111111111111,
    (10.7769, 106.7009),
    (95, 'GPS')
);

SELECT coordinates, quality
FROM geo_samples_by_id
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Here:

- `coordinates` stores **latitude at position 0** and **longitude at position 1** by **application convention**. Cassandra only knows there are two `double` values; it has no awareness of coordinate systems or which position is latitude.
- `quality` stores an **int score at position 0** and a **text source code at position 1**.
- Tuple literals use **parentheses**: `(10.7769, 106.7009)`.
- Tuples have **fixed arity**: if the schema is `tuple<int,text>`, the literal must account for both positions. A position may be `null` where appropriate, but you cannot omit positions while preserving meaning.

Because tuples **have no field names**, element order is part of the data contract. If client A expects `(lat, lon)` while client B writes `(lon, lat)`, the data passes CQL type checks while being **semantically wrong**.

### 2.2. Tuples Are Always Frozen

In Cassandra, a tuple is **always treated as frozen** even without writing the `frozen` keyword in its declaration. Therefore:

~~~cql
-- Valid: replace the entire tuple.
UPDATE geo_samples_by_id
SET coordinates = (10.7800, 106.7050)
WHERE sample_id = 11111111-1111-4111-8111-111111111111;
~~~

Do not expect an index update like `coordinates[0]` as with a non-frozen `list`; a tuple is **not a list**. To change only the latitude, the client must build a **new tuple containing both valid values** and replace the whole value.

Important consequences:

- **Value-level atomicity:** replacing a tuple mutates a single monolithic value; half of a new tuple will never merge independently with half of an old tuple like a non-frozen UDT.
- **Concurrency:** two clients reading a tuple and editing different positions can overwrite each other's changes when each replaces the entire tuple.
- **Overhead:** very small pairs like coordinates are fine; with many large elements, changing one spot forces resending the whole value.
- **Lookups:** Cassandra does not create a query path for "all rows where tuple element 0 is in range X" merely because the column is a tuple.

### 2.3. When Is a Tuple Worse Than a UDT?

Tuples work well for fixed data that is **simple and self-evidently positional**, such as a coordinate pair in a well-documented system.

However, for `(street, ward, city, postalCode, countryCode)`, using `tuple<text,text,text,text,ascii>` produces hard-to-remember positions, fragile field additions, and poor readability in both Java and CQL. A **UDT with named fields** fits much better there.

**Rule of thumb:** if a tuple has more than 2–3 elements or needs a comment explaining "what position 3 actually means," evaluate a UDT or separate CQL columns before finalizing the design.

## 3. UDT: A Group of Named, Strongly Typed Fields

### 3.1. CREATE TYPE in a Keyspace

A **user-defined type (UDT)** is a named structure containing an ordered list of **named and typed** fields. A UDT is defined **inside a keyspace** and then used by tables in that keyspace.

~~~cql
-- Assumes the application keyspace is already selected via USE or client config.
CREATE TYPE postal_address (
    street text,
    ward text,
    city text,
    postal_code text,
    country_code ascii
);
~~~

Fields are defined **in order**. That order matters for codecs/serialization and schema evolution even when the application primarily accesses fields by **name**. Never think of a UDT as simply a `map<text,text>`: a UDT has a **fixed schema and per-field types**, whereas a map has dynamic keys and uniform value types.

UDT literals in CQL use **unquoted field names**, not string keys:

~~~cql
{
    street: '42 Nguyen Hue',
    ward: 'Ben Nghe',
    city: 'Ho Chi Minh City',
    postal_code: '700000',
    country_code: 'VN'
}
~~~

Unlike a `map<text,text>` literal such as `{'theme': 'dark'}`, identifiers like `street` and `city` in a UDT literal are **field names declared in the type**.

A UDT literal may **omit some fields**; those fields evaluate to `null` inside that UDT value. This differs from whether the entire UDT column itself is present or absent in a row.

### 3.2. Why Reuse UDTs?

If `postal_address` appears across multiple tables, defining the type once lets the same field schema serve different roles:

- `current_address postal_address`: mutable current address on a customer profile.
- `shipping_address frozen<postal_address>`: **snapshot at order placement time**.
- `billing_address frozen<postal_address>`: invoicing address that must remain intact for records.

Reusing a **type definition** does not synchronize column values across tables. Updating `current_address` does not alter `shipping_address` snapshots in past orders—which is usually the exact business intent.

### 3.3. Limits of UDTs

A UDT is useful when a group of fields acts as a **value attached to a row**. It does **not** provide:

- **Foreign-key relationships** to other rows;
- **Automatic indexes** on individual fields;
- **Business validation** (valid country codes, country-specific postal codes);
- **Multi-table ACID transactions** across rows containing that type;
- **Cluster-wide uniqueness** on a field inside the UDT.

If you frequently query `postal_address.city` to find **all customers in a city**, design a city-keyed access path rather than merely putting `city` inside a UDT.

## 4. Frozen UDT: Monolithic Snapshot

A `frozen<postal_address>` field is handled by Cassandra **as a single complete value inside one cell**. When updating it, the application replaces **the entire address** instead of mutating individual fields on the server.

Example table for "view a customer's order history by month":

~~~cql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    order_month text,
    ordered_at timestamp,
    order_id uuid,
    shipping_address frozen<postal_address>,
    dropoff_point tuple<double, double>,
    total_minor bigint,
    currency_code ascii,
    PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);
~~~

Here:

- **`(customer_id, order_month)`** is the partition key, e.g., `order_month = '2026-11'` under UTC or an agreed business calendar.
- **`ordered_at, order_id`** are clustering columns, sorting orders chronologically and breaking ties within the same millisecond.
- **`shipping_address frozen<postal_address>`** holds the **address snapshot**; later updates to the customer's profile address do not alter historical order records.
- **`dropoff_point tuple<double,double>`** holds a latitude/longitude pair per application convention; tuples are inherently frozen.
- **`total_minor bigint`** and `currency_code ascii` illustrate storing money in minor units with an explicit currency code; never use `double` for monetary reconciliation.

~~~cql
INSERT INTO orders_by_customer_month (
    customer_id, order_month, ordered_at, order_id,
    shipping_address, dropoff_point, total_minor, currency_code
) VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11',
    '2026-11-21T04:00:00Z',
    33333333-3333-4333-8333-333333333333,
    {
        street: '42 Nguyen Hue',
        ward: 'Ben Nghe',
        city: 'Ho Chi Minh City',
        postal_code: '700000',
        country_code: 'VN'
    },
    (10.7769, 106.7009),
    199000,
    'VND'
);
~~~

Querying using the designed key:

~~~cql
SELECT ordered_at, order_id, shipping_address,
       dropoff_point, total_minor, currency_code
FROM orders_by_customer_month
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND order_month = '2026-11'
LIMIT 50;
~~~

`frozen` does not make a column **historically immutable**: an `UPDATE` can still replace or delete a frozen column. Snapshot immutability must be enforced by application write rules, access controls, and audit processes.

### 4.1. Replace the Whole Value, Not Individual Fields

~~~cql
-- Valid: replace the entire frozen UDT with a new value.
UPDATE orders_by_customer_month
SET shipping_address = {
    street: '10 Le Loi',
    ward: 'Ben Nghe',
    city: 'Ho Chi Minh City',
    postal_code: '700000',
    country_code: 'VN'
}
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND order_month = '2026-11'
  AND ordered_at = '2026-11-21T04:00:00Z'
  AND order_id = 33333333-3333-4333-8333-333333333333;
~~~

There is no syntax like `SET shipping_address.city = ...` **for a frozen UDT**. To change the city inside a frozen UDT, you must supply and rewrite all remaining fields from a complete, trusted source.

With two concurrent clients updating:

~~~text
Initial state:
{street: '42 Nguyen Hue', city: 'Ho Chi Minh City'}

Client A reads and edits street
Client B reads and edits city

A writes full frozen value with new street, old city
B writes full frozen value with old street, new city

Outcome can lose one of the edits,
depending on conflict resolution and write timestamp metadata.
~~~

Frozen values do not automatically merge field-level edits. If business logic requires independent writers updating different fields concurrently, consider a **non-frozen UDT** or separate columns along with concurrency policies.

## 5. Non-Frozen UDT: Updating Individual Fields

In Cassandra versions supporting **non-frozen UDTs** (starting from Cassandra 3.6's CQL line and later versions), individual fields can be updated or deleted independently when the schema allows. Before relying on this, **confirm your deployed Cassandra version/distribution**; restrictions around nested types and collections can vary across versions.

Example customer profile with a mutable current address:

~~~cql
CREATE TABLE customer_profiles_by_id (
    customer_id uuid PRIMARY KEY,
    display_name text,
    current_address postal_address,
    updated_at timestamp
);

INSERT INTO customer_profiles_by_id (
    customer_id, display_name, current_address, updated_at
) VALUES (
    22222222-2222-4222-8222-222222222222,
    'Nguyen Ha',
    {
        street: '42 Nguyen Hue',
        ward: 'Ben Nghe',
        city: 'Ho Chi Minh City',
        postal_code: '700000',
        country_code: 'VN'
    },
    '2026-11-21T04:10:00Z'
);
~~~

Update only the city without requiring the application to rebuild the whole address:

~~~cql
UPDATE customer_profiles_by_id
SET current_address.city = 'Ha Noi',
    updated_at = '2026-11-21T04:15:00Z'
WHERE customer_id = 22222222-2222-4222-8222-222222222222;
~~~

The `current_address.city` syntax works because **the UDT column is non-frozen**. Other fields such as `street` and `postal_code` do not have to be rewritten merely because `city` changed.

To delete a single field of a non-frozen UDT:

~~~cql
DELETE current_address.postal_code
FROM customer_profiles_by_id
WHERE customer_id = 22222222-2222-4222-8222-222222222222;
~~~

This deletion writes a **tombstone** for that specific field. Non-frozen UDTs store fields as independently updatable components; monitor write/tombstone overhead and never assume a non-frozen UDT acts as a single "atomic object" sharing one version across all fields.

### 5.1. Why Does Non-Frozen Still Require Concurrency Handling?

Two clients updating **two different fields** may collide less often than replacing an entire frozen UDT, yet that does not mean:

- Changing `city` and `postal_code` in two separate statements will always be observed as one atomic business transaction.
- Cassandra automatically enforces cross-field address consistency rules.
- Fields share the same TTL or write timestamp when updated at different times.
- Another client replacing **the entire UDT** won't overwrite fields recently edited by someone else.

If changing an address must be an atomic versioned transition, consider a **frozen snapshot + version/LWT**, or design the row/mutation unit accordingly. When frequent independent field edits occur, non-frozen UDTs can be more efficient, though retries and conflicts must still be handled.

### 5.2. When to Use Separate Columns Instead of a UDT?

You do not have to create a UDT just because columns are semantically related. For example:

~~~cql
CREATE TABLE customer_contact_by_id (
    customer_id uuid PRIMARY KEY,
    street text,
    ward text,
    city text,
    country_code ascii,
    phone text
);
~~~

Standalone columns make selecting subsets of fields and updating explicitly straightforward. UDTs fit better when you want to **reuse a shared value model** across multiple tables or treat the field group as a named domain unit.

Between the two, weigh schema reuse, field stability, query patterns, concurrency, migrations, and Java API ergonomics. **Never choose UDTs just to build deeply nested structures**, as nesting does not alter the wide-column table model.

## 6. frozen and Actual Storage Semantics

### 6.1. One Cell vs. Multiple Cells

A simplified mental model:

~~~text
Row for customer_id = C

frozen<postal_address> column:
  shipping_address -> [serialized address: street, ward, city, ...]
  (a single value/cell at the Cassandra level)

Non-frozen postal_address column:
  current_address.street       -> "42 Nguyen Hue"
  current_address.ward         -> "Ben Nghe"
  current_address.city         -> "Ho Chi Minh City"
  current_address.postal_code  -> "700000"
  current_address.country_code -> "VN"
  (fields behave as individually updatable cells/values)
~~~

This diagram illustrates the **logical unit of mutation**, not byte-for-byte SSTable file layouts across all versions. Key takeaways for applications:

- **Frozen:** replace/DELETE the entire value; no single nested field mutations.
- **Non-frozen:** can mutate/delete individual fields per supported CQL syntax.
- **Tuple:** always frozen, even without writing `frozen<tuple<...>>`.
- **Nested UDTs/collections:** nesting rules dictate where `frozen` is required; verify against your CQL version and schema instead of assuming every combination is legal.

### 6.2. Bounded Atomicity

When Cassandra applies a mutation writing a frozen value, that value is handled as a **single unit**—it will not splice one new field from writer A with one new field from writer B into a hybrid object under non-frozen semantics.

However, "a single value" does **not** mean:

- Writes spanning multiple tables or partitions become an ACID transaction.
- Every reader gets linearizable consistency without designing conditional reads/writes.
- Writing a frozen snapshot creates a system-wide unique identifier.
- Cassandra prevents lost updates when two writers overwrite the entire value concurrently.

Cassandra lets you tune consistency levels and supports conditional operations in specific scenarios; **versioning and idempotency rules must still be designed for the domain**.

### 6.3. TTL, NULL, UNSET, and Tombstones

A **frozen UDT** is a single-value column; TTL, NULL, and deletes operate at the level of that column value. A **non-frozen UDT** allows per-field updates/deletes, meaning individual fields can carry **different write timestamps or TTLs** depending on how mutations were applied.

Summary table:

| Scenario | Frozen UDT / Tuple | Non-Frozen UDT |
|---|---|---|
| Omitted in regular INSERT | Existing column untouched | Existing UDT untouched if column omitted from mutation |
| Bind **UNSET** to whole column | Skips entire value | Skips entire UDT in an applicable operation |
| Write **NULL** to whole column | Deletes value, creates tombstone per rules | Deletes UDT/fields per supported mutation |
| Edit one field | Replace entire value | `SET address.field = ...` |
| Delete one field | Single-field delete not supported | `DELETE address.field ...` |
| Can fields have different TTLs? | No within a single frozen cell | Yes when fields are written separately |

**Caution with UDT literals omitting fields:** when constructing an **entire frozen value**, fields omitted from the literal become **NULL inside the new UDT**. Never treat a literal containing only `{city: 'Ha Noi'}` as "patch city and keep all other fields" on a frozen address: it is **a brand-new value**, and omitted fields are not inherited from the old version.

If a PATCH API distinguishes **omitted**, **explicit null**, and **new value**, map them properly to `UNSET`, `NULL`, or field-level mutations. Never avoid tombstones by turning genuine deletions into UNSET; doing so leaves stale data alive.

### 6.4. Size of a Single Value

A large frozen UDT forces clients to read and rewrite the entire value whenever one field changes. Nor is a non-frozen UDT with dozens of fields or huge nested collections always wise: unboundedly growing data belongs in separate keyed rows.

For large payloads or files, use object storage and keep URIs/metadata in Cassandra. For millions of addresses or transactions, never cram them all into one collection or UDT in a single row; partition them so Cassandra can paginate and distribute load.

## 7. Tuple/UDT and PRIMARY KEY: Why Prefer Stable Keys?

A partition key in Cassandra is **encoded and hashed** to determine tokens and replicas. Clustering columns are **compared in order** within a partition. Keys should therefore be stable, well-defined, and aligned with queries.

Type-wise, certain **frozen** composite types may be permitted in key positions depending on the CQL version, yet that does not make them good default keys. Putting an entire address into a primary key causes problems:

1. **Any field edit changes the key.** Fixing punctuation in an address moves the row to a different partition.
2. **Canonicalization** (casing, Vietnamese diacritics, country codes, postal formatting) becomes a fragile part of row identity.
3. **Business uniqueness** of addresses is ambiguous: two customers can share an address.
4. **Querying by one field** like `city` is not automatically optimized just because `city` sits inside a composite key.
5. Serialized frozen key bytes across schema/version upgrades require careful governance.

That is why in `orders_by_customer_month`, the keys are **`customer_id`, `order_month`, `ordered_at`, `order_id`**, while `shipping_address frozen<postal_address>` is purely a **data column**. Keep **IDs/query paths** cleanly separated from **domain snapshots**.

If you need exact lookups by `order_id` alone, add an `orders_by_id` table or an ID → partition-key mapping; Cassandra cannot efficiently look up by `order_id` alone when the table's partition key requires `(customer_id, order_month)`.

## 8. Java Driver 4.x: TupleValue and UdtValue

In Java Driver 4.x, these two CQL types map to dedicated metadata/value objects rather than plain `List<Object>` or arbitrary POJOs by default:

| CQL | Java Type Metadata | Java Value | Read/Write API |
|---|---|---|---|
| `tuple<double,double>` | `TupleType` | `TupleValue` | `getTupleValue`, `setTupleValue` |
| `postal_address` or `frozen<postal_address>` | `UserDefinedType` | `UdtValue` | `getUdtValue`, `setUdtValue` |
| `text` field inside UDT | Field type metadata | `String` | `udtValue.getString("city")`, `setString("city", ...)` |

Note: Java Driver does not automatically bind arbitrary Java POJOs to UDT columns; use `UdtValue` or a properly configured **Mapper/codec**. Because UDTs are scoped to a keyspace with specific field ordering, retrieving **type metadata from the schema or prepared statement** is far safer than constructing types manually.

### 8.1. Getting Type Metadata from a Prepared Statement, Building Values, and Binding

Example writing an order into `orders_by_customer_month`. Assume `session` is a `CqlSession` connected to the keyspace defining `postal_address`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.data.TupleValue;
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.TupleType;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

import java.time.Instant;
import java.util.UUID;

// CqlSession session = ...; // Connection managed outside this example.

PreparedStatement insertOrder = session.prepare(
    "INSERT INTO orders_by_customer_month "
  + "(customer_id, order_month, ordered_at, order_id, "
  + " shipping_address, dropoff_point, total_minor, currency_code) "
  + "VALUES (:customer_id, :order_month, :ordered_at, :order_id, "
  + " :shipping_address, :dropoff_point, :total_minor, :currency_code)");

// Driver knows the exact bind variable types from the server schema.
UserDefinedType addressType = (UserDefinedType)
    insertOrder.getVariableDefinitions()
        .get("shipping_address").getType();

TupleType pointType = (TupleType)
    insertOrder.getVariableDefinitions()
        .get("dropoff_point").getType();

UdtValue address = addressType.newValue()
    .setString("street", "42 Nguyen Hue")
    .setString("ward", "Ben Nghe")
    .setString("city", "Ho Chi Minh City")
    .setString("postal_code", "700000")
    .setString("country_code", "VN");

TupleValue point = pointType.newValue()
    .setDouble(0, 10.7769)   // Latitude per contract.
    .setDouble(1, 106.7009); // Longitude per contract.

UUID customerId =
    UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID orderId =
    UUID.fromString("33333333-3333-4333-8333-333333333333");

BoundStatement bound = insertOrder.boundStatementBuilder()
    .setUuid("customer_id", customerId)
    .setString("order_month", "2026-11")
    .setInstant("ordered_at", Instant.parse("2026-11-21T04:00:00Z"))
    .setUuid("order_id", orderId)
    .setUdtValue("shipping_address", address)
    .setTupleValue("dropoff_point", point)
    .setLong("total_minor", 199000L)
    .setString("currency_code", "VND")
    .build();

session.execute(bound);
~~~

Explanation:

- `getVariableDefinitions().get("shipping_address").getType()` retrieves the bind variable metadata matching the deployed UDT.
- `addressType.newValue()` creates a `UdtValue` with named fields.
- `pointType.newValue()` creates a `TupleValue` with positions 0 and 1.
- `setUdtValue` and `setTupleValue` bind values using the right codecs.
- UUIDs are generated/fetched **once** and **reused on retries**. Never generate a new `orderId` after a timeout, or you risk creating duplicate rows for the same order.

**Mutability note:** driver `UdtValue` and `TupleValue` instances are **mutable value objects**, whereas `BoundStatement` is **immutable**. If multiple threads share and mutate a bound `UdtValue` during async execution, race conditions or corrupted data can occur. Create dedicated instances/snapshots per request before submitting.

### 8.2. Reading Back from a Row

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.data.TupleValue;
import com.datastax.oss.driver.api.core.data.UdtValue;

PreparedStatement findOrders = session.prepare(
    "SELECT ordered_at, order_id, shipping_address, dropoff_point "
  + "FROM orders_by_customer_month "
  + "WHERE customer_id = ? AND order_month = ? LIMIT 50");

for (Row row : session.execute(
        findOrders.bind(customerId, "2026-11"))) {

    UdtValue shipping = row.getUdtValue("shipping_address");
    if (shipping != null) {
        String city = shipping.getString("city");
        String street = shipping.getString("street");
    }

    TupleValue location = row.getTupleValue("dropoff_point");
    if (location != null &&
        !location.isNull(0) &&
        !location.isNull(1)) {

        double latitude = location.getDouble(0);
        double longitude = location.getDouble(1);
    }
}
~~~

A **UDT column can be null**. A **non-null UDT can still contain null fields** if omitted from the literal/source. Likewise, tuples can hold null elements, so check `isNull(index)` before calling primitive getters (`getDouble`) when missing values are allowed.

### 8.3. Updating a Non-Frozen UDT from Java

To update the city of `customer_profiles_by_id.current_address`, you do not need to build a `UdtValue` for the entire address:

~~~java
PreparedStatement updateCity = session.prepare(
    "UPDATE customer_profiles_by_id "
  + "SET current_address.city = ?, updated_at = ? "
  + "WHERE customer_id = ?");

session.execute(
    updateCity.boundStatementBuilder()
        .setString(0, "Ha Noi")
        .setInstant(1, Instant.parse("2026-11-21T04:15:00Z"))
        .setUuid(2, customerId)
        .build()
);
~~~

This is the benefit of a **non-frozen UDT** when editing specific fields. If `current_address` were declared **frozen**, that statement would fail; you would have to build a full `UdtValue` with every field and bind it as a whole value.

### 8.4. Retrieving UserDefinedType from Schema Metadata

Beyond prepared statements, you can obtain the type from keyspace metadata:

~~~java
import com.datastax.oss.driver.api.core.type.UserDefinedType;

// Using example keyspace "shop_ks".
UserDefinedType addressType = session.getMetadata()
    .getKeyspace("shop_ks")
    .flatMap(ks -> ks.getUserDefinedType("postal_address"))
    .orElseThrow(() -> new IllegalStateException("UDT not yet in schema"));
~~~

After `CREATE TYPE` or `ALTER TYPE`, clients must observe the updated schema. In a distributed cluster, wait for **schema agreement** and ensure the session/driver has refreshed metadata before constructing/binding `UdtValue` for the new type. Avoid hand-constructing types via internal APIs with mismatched field orders, as data can be encoded incorrectly or become unreadable.

## 9. Nested Types and Collections: When Is frozen Required?

A common requirement is "each user has multiple addresses labeled home/work." For a **small, bounded** number of addresses, you can store a map of **frozen UDTs**:

~~~cql
CREATE TABLE address_book_by_user (
    user_id uuid PRIMARY KEY,
    addresses map<text, frozen<postal_address>>
);
~~~

Example:

~~~cql
INSERT INTO address_book_by_user (user_id, addresses)
VALUES (
    44444444-4444-4444-8444-444444444444,
    {
        'home': {
            street: '42 Nguyen Hue',
            ward: 'Ben Nghe',
            city: 'Ho Chi Minh City',
            postal_code: '700000',
            country_code: 'VN'
        },
        'work': {
            street: '10 Le Loi',
            ward: 'Ben Nghe',
            city: 'Ho Chi Minh City',
            postal_code: '700000',
            country_code: 'VN'
        }
    }
);
~~~

In `map<text, frozen<postal_address>>`:

- The map **can** be updated per entry, e.g., `addresses['home']`.
- **The entry value** is a frozen UDT, so changing the city of `home` requires **replacing the entire `home` address value**; no free-form nested field mutation applies.
- The map still carries design limits: it only fits when keys like `"home"/"work"/...` are few; if there are thousands of addresses with independent queries/lifecycles, use **one row per address**.
- Complex nesting faces syntax restrictions depending on CQL version. Check your running version's documentation before picking nested non-frozen types.

Example replacing the entire `home` entry:

~~~cql
UPDATE address_book_by_user
SET addresses['home'] = {
    street: '99 Dong Khoi',
    ward: 'Ben Nghe',
    city: 'Ho Chi Minh City',
    postal_code: '700000',
    country_code: 'VN'
}
WHERE user_id = 44444444-4444-4444-8444-444444444444;
~~~

**Never treat a map of frozen UDTs as a miniature address table that can be arbitrarily paginated.** Entry-level reads/writes and tombstone mechanics do not replace clustering columns, pagination, and partition distribution. To find all user addresses in a given city, design a dedicated query table.

## 10. UDT Schema Evolution: Adding Fields, Updating Contracts, and Migrations

A UDT's schema lives in its keyspace. For example, suppose the application wants to add a district field to addresses:

~~~cql
ALTER TYPE postal_address ADD district text;
~~~

Under CQL semantics, **UDT values written before adding the field** have no stored value for `district`; the new field reads back as **NULL** until populated. This is not an automatic backfill migration.

Rules to follow:

1. **Start with backwards-compatible changes**, such as adding an optional field; allow older clients unaware of the new field to keep running during rollout.
2. **Wait for schema agreement** across the cluster and verify driver metadata/codecs; especially for `frozen<UDT>`, decoding depends on exact field definitions and order.
3. **Never repurpose an existing field** by keeping its name while changing its unit/format. For example, changing `postal_code` from text to numeric loses leading zeros and breaks international codes.
4. **Version data when needed:** for finalized orders, schema or display changes must distinguish historical snapshots from current profile addresses.
5. **Run controlled backfills** when a new field becomes business-mandatory; count missing rows, retry with stable IDs, and reconcile.
6. **Never arbitrarily DROP TYPE** while referenced by tables/UDTs/functions. CQL typically rejects dropping referenced types.

An `ALTER TYPE ... RENAME` command may be supported in specific CQL versions, yet renaming a field changes the contract for code, prepared statements, mappers, APIs, and schema metadata. Never treat it as harmless merely because stored bytes remain readable.

### 10.1. Tuples Are Difficult to Evolve by Field

Tuples **have no field names**, so clients read elements by **index**. If one team uses `tuple<text,int>` while another swaps positions to `tuple<int,text>`, the data violates the type contract.

Even appending elements at the end alters column type definitions and codecs and should not be assumed automatically compatible. For domain structures expected to gain or modify fields, **named-field UDTs** or **separate columns** are far easier to maintain.

### 10.2. Frozen Does Not Automatically Upgrade Old Data

A `frozen<postal_address>` written before `district` was added does not magically contain a real `district`. If historical orders must display districts accurately, you may need original source records/events rather than inferring them from the new schema.

Issuing an `UPDATE` to rewrite frozen values on old orders can also destroy snapshot fidelity. Distinguish **schema evolution** (which fields can be read/written) from **business migration** (correct values on historical records).

## 11. Retries, Consistency, and Updating Composite Values

### 11.1. Retries After Timeout and Lost Updates

In Cassandra, a write may succeed on some replicas even when the client times out. Therefore:

- With **frozen UDTs/tuples**, retrying with the exact same **primary key and value** for the same request is easier to reason about than recomputing a fresh value from mutated state—still check write timestamps and concurrency.
- With **non-frozen UDTs**, retrying the same single-field update with the same value does not create duplicate fields; however, conflicts with other writers still depend on write metadata and application coordination.
- For **business events**, generate `order_id` **once** and reuse it across every retry. Never let a retry create a second order.
- If an operation updates both profile and multiple history tables, never assume independent CQL statements form a multi-partition ACID transaction.

**Consistency levels** like `LOCAL_QUORUM` control replica acknowledgment counts; they do not decide "which client is newer in wall-clock time" for two concurrent frozen overwrites.

### 11.2. Conditional Writes

If the domain requires "update the address only if version is still 5," you can store `version int` and use a **lightweight transaction (LWT)** where supported by your CQL/Cassandra version:

~~~cql
-- Illustrates optimistic concurrency on a single row.
-- Assumes the table has a version int column alongside customer_id.
UPDATE customer_profiles_versioned
SET version = 6
WHERE customer_id = 22222222-2222-4222-8222-222222222222
IF version = 5;
~~~

This illustrates **conditional version checking**, not a full table definition; in production, include the address fields being changed inside **the same conditional UPDATE** so the version check binds atomically to the mutation. LWT carries significantly higher Paxos overhead than normal writes; do not enable it everywhere by default just to paper over unclear concurrency design.

If the system must deduplicate events, dedicated audit records or identity tables may fit better than a bare version field alone.

## 12. Replication, Compaction, Repair, and Data Size

### 12.1. Replication and Repair

Cassandra replicates **mutations/cells** based on partition keys and replication strategies. For `frozen<UDT>`, replicas store the **packed value**; for non-frozen UDTs, individual fields can carry independent update metadata. **Repair** converges replica state according to Cassandra mechanics, yet cannot fix logic bugs such as swapping `latitude` and `longitude` inside a tuple.

### 12.2. Compaction and Tombstones

When values are deleted or overwritten, Cassandra writes deletion markers/tombstones to stop old values from resurrecting on replicas. Updating/deleting a non-frozen UDT field generates field-level mutations; deleting or replacing a frozen value operates at the whole-value level. **Compaction** merges SSTables and purges eligible tombstones; it cannot turn a huge UDT into a paginated multi-row structure.

If you frequently edit a single field inside a very large object, re-evaluate the **unit of mutation** and whether rewriting the whole frozen value causes unnecessary network and GC overhead.

### 12.3. Partition Size

`orders_by_customer_month` bounds partitions by customer and month, yet **does not guarantee small partitions** if a single customer places huge numbers of orders. Measure rows per partition, address UDT size, total bytes, tombstones, and p95/p99 read/write latencies, and adopt smaller buckets or sharding if needed.

**Do not shove thousands of addresses** into `map<text,frozen<postal_address>>` inside a single row just because CQL permits it. When addresses need independent search, pagination, editing, or deletion, a table with `PRIMARY KEY ((customer_id, bucket), address_id)` or a query-aligned key is far easier to operate.

### 12.4. Protecting Personal Data

Addresses and coordinates can be sensitive PII. Packing fields into a UDT **does not automatically encrypt them or enforce field-level access control**. Apply proper authorization, log masking, retention/TTL, and deletion workflows. Never log `UdtValue.getFormattedContents()` indiscriminately, as it can dump full personal addresses into logs.

## 13. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using a long tuple to store an address | Easy to mix up indices, hard to evolve schema | Use a named-field UDT or separate columns |
| Swapping `latitude` and `longitude` in a tuple | Wrong data passes codec checks silently | Document order, validate bounds, write boundary tests |
| Expecting `coordinates[0]` updates on a tuple | Tuples are always frozen; no list-style index mutations | Construct a new tuple and replace the whole value |
| Using `frozen<UDT>` while expecting `address.city = ...` | CQL forbids field-level updates on frozen values | Use non-frozen UDT or replace whole value |
| Assuming frozen means never updatable | Whole value can still be overwritten | Protect snapshots via business rules |
| Patching a frozen UDT with a literal containing only `city` | Other fields in the new value become null | Supply the complete validated value |
| Rewriting an entire non-frozen UDT from concurrent read-modify-write clients | Lost updates or invariant violations | Mutate individual fields, use version/LWT if needed |
| Treating a UDT as an index on `city` | No automatic cluster-wide field search | Build a city table or benchmarked index |
| Using a frozen address as an identifier key | Key changes when address edits occur; hard canonicalization | Use stable `uuid`/text keys; keep address as value |
| Treating non-frozen UDTs as multi-field transactions | Independent steps still face race/partial states | Align mutation/condition boundaries properly |
| Altering a UDT without refreshing Java Driver metadata | Codecs mismatch new schema definitions | Wait for schema agreement, refresh metadata, test migrations |
| Letting a map/UDT grow unboundedly | Heavy rows/partitions, poor pagination | Use multi-row tables with query keys |
| Expecting repair to fix swapped tuple fields | Replicas converge on whatever wrong data was written | Enforce app validation/QA and controlled backfills |
| Logging full UDTs containing personal addresses | Sensitive data leakage | Redact logs and restrict log access |

## 14. Scenario Exercises

### Exercise 1 — Choosing Types

An application needs to store:

1. Two numbers `latitude, longitude` attached to a snapshot.
2. Shipping address captured at checkout; must not change if the profile address changes later.
3. Current address where users independently edit `ward`/`city`/`postal_code`.
4. All historical addresses ever used by users, spanning millions of records needing pagination.

**Hint:** (1) `tuple<double,double>` with clear positional conventions; (2) `frozen<postal_address>`; (3) non-frozen `postal_address` (when supported by version) or separate columns; (4) **a multi-row table** with address ID/bucket and appropriate clustering.

### Exercise 2 — Is Frozen Truly Immutable?

`orders_by_customer_month.shipping_address` is declared `frozen<postal_address>`. A client sends `UPDATE SET shipping_address = { ... }` with a new address and matching primary key.

**Answer:** Cassandra **can update** the entire frozen value. `frozen` only prevents field-level updates, not overwriting the snapshot itself; historical immutability must be enforced by business rules.

### Exercise 3 — Concurrent Update Race

Initially `address = \{street: 'A', city: 'X'\}`. Client 1 changes street to B, client 2 changes city to Y; both read the old snapshot and overwrite the whole `frozen<address>`.

**Question:** is the final state guaranteed to be `{street: 'B', city: 'Y'}`?

**Answer:** no. Two full-value replacements can overwrite one change. Consider non-frozen field-level mutations, or versioning/conditional writes if the domain treats the entire address as an atomic versioned unit.

### Exercise 4 — UDT Literal Missing Fields

~~~cql
-- Column shipping_address is frozen<postal_address>.
UPDATE orders_by_customer_month
SET shipping_address = {city: 'Ha Noi'}
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND order_month = '2026-11'
  AND ordered_at = '2026-11-21T04:00:00Z'
  AND order_id = 33333333-3333-4333-8333-333333333333;
~~~

**Question:** is `street` preserved?

**Answer:** never assume it is preserved. This statement replaces **the entire frozen value**, so fields omitted from the literal become **null** in the new value. For field-level PATCHes, use a non-frozen UDT or build a complete frozen value under concurrency controls.

### Exercise 5 — Java Driver

A prepared statement binds `shipping_address frozen<postal_address>` and `dropoff_point tuple<double,double>`. You need to bind both in Java.

**Hint:** fetch `UserDefinedType`/`TupleType` from `prepared.getVariableDefinitions().get("...").getType()`, call `newValue()`, set named fields on `UdtValue` and indexed elements on `TupleValue`, then call `setUdtValue`/`setTupleValue`. Do not hand-serialize JSON or pass `List<Object>` hoping the driver infers the schema.

### Exercise 6 — Querying by Address

The orders table is partitioned by `(customer_id, order_month)` and has `shipping_address frozen<postal_address>`. Product asks to "find all orders delivered to Hanoi in the last 7 days."

**Answer:** a UDT column does not provide cluster-wide lookups by `city`. Design a query table keyed by city/day with buckets and IDs, or an index/search mechanism benchmarked for your version and workload; keep it synchronized when order addresses are modified.

## 15. Checklist Before Using tuple, UDT, and frozen

- [ ] Does the structure need **fixed positions** (tuple) or **clear named fields** (UDT)?
- [ ] Are tuple element positions documented and tested to prevent swapping?
- [ ] Is the UDT defined in the right keyspace with stable field types and semantics?
- [ ] Should the column **replace whole snapshots** (frozen) or **edit individual fields** (non-frozen)?
- [ ] Is it clear that **tuples are always frozen**, with no single-element updates?
- [ ] For frozen values, do all PATCH operations build a **complete value** instead of supplying one field and nulling others?
- [ ] For non-frozen UDTs, do the Cassandra version and nesting rules support this schema?
- [ ] Have concurrency, TTL, tombstones, and versioning been evaluated for the mutation unit?
- [ ] Are column-level **NULL/UNSET** clearly separated from NULL fields inside a UDT?
- [ ] Do queries have aligned **partition keys/clustering columns** rather than relying on UDTs to index fields?
- [ ] Does the Java Driver use `UdtValue`/`TupleValue`, retrieving metadata from the schema or prepared statement?
- [ ] After `ALTER TYPE`, have clients refreshed metadata, tested read/write compatibility, and planned backfills if needed?
- [ ] Are field counts, frozen value sizes, and partition sizes bounded and monitored in production?
- [ ] Do retries keep the same primary key, preventing duplicate orders after timeouts?
- [ ] Have replication, consistency, compaction, repair, data privacy, and auditing been addressed?

## References

- [Apache Cassandra — CQL Data Types: UDT and Tuple](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — Data Manipulation (updating non-frozen UDT fields)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra — CREATE TABLE and frozen UDTs](https://cassandra.apache.org/doc/stable/cassandra/reference/cql-commands/create-table.html).
- [Apache Cassandra Java Driver 4.x — UDTs](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/).
- [Apache Cassandra Java Driver 4.x — Tuples](https://apache.github.io/cassandra-java-driver/4.19.0/core/tuples/).

**Remember:** **`tuple`** models **positional** groups and is **always frozen**; **UDT** models **named** field groups and can be frozen or non-frozen where supported by schema and version. **Frozen = replace the entire value**, with no independent field-level updates. In Cassandra, this choice determines mutation units, concurrency, tombstones, and Java codecs; meanwhile, partition keys, clustering, replication, and query-driven design determine how efficiently data is retrieved.
