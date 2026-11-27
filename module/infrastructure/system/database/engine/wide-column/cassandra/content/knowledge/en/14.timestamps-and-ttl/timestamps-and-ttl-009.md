# TTL on Collection/UDT Elements Based on Storage Layout in Apache Cassandra

## 1. Does a Collection Always Share a Single Expiration Time?

In **Apache Cassandra**, a **distributed wide-column** database management system, TTL (*time to live*) defines how long a value remains live data. In the **Timestamps and TTL** chapter, there is a crucial detail: **the storage unit of a value determines the scope of TTL**. A column of type `map`, `set`, `list`, or **user-defined type (UDT)** can be stored as **multiple cells** or as **a single cell**, depending on whether `frozen` is used.

Imagine two structures holding the same two attributes:

- Non-frozen `properties map<text, text>`: Cassandra can store each map entry in separate cells. Each written entry can carry its own **write timestamp and TTL**.
- `snapshot frozen<map<text, text>>`: the entire map value is serialized into **one cell**. When this cell has a TTL, the whole `snapshot` value expires together; you cannot renew a single entry by updating by key.

The same applies to **non-frozen UDTs** (individual fields can be written independently) and **frozen UDTs** (the entire object acts as one monolithic value).

TTL is a data lifecycle management tool. It **does not guarantee immediate physical deletion** upon expiration: Cassandra relies on expiration/tombstone metadata and compaction/repair mechanisms to prevent stale replicas from resurrecting old data.

## 2. Distinguishing `frozen` and Non-`frozen` at the Storage Level

In the wide-column model, a partition holds rows, and each row holds cells. For *complex types*, CQL can map **one logical column** to **multiple physical cells**.

```text
Row: profile_id = P
|
|-- attributes map<text,text> (NON-frozen)
|     |-- attributes['tier']     -> cell A, write timestamp TA, TTL A
|     |-- attributes['locale']   -> cell B, write timestamp TB, TTL B
|     +-- attributes['temporary']-> cell C, write timestamp TC, TTL C
|
|-- contact address_udt (NON-frozen)
|     |-- contact.street  -> cell D, TTL D
|     |-- contact.city    -> cell E, TTL E
|     +-- contact.country -> cell F, TTL F
|
|-- snapshot frozen<map<text,text>>
|     +-- {tier:'pro', locale:'vi'} -> ONE cell, ONE TTL
|
+-- frozen_contact frozen<address_udt>
      +-- {street:...,city:...,country:...} -> ONE cell, ONE TTL
```

| Structure | Conceptual storage layout | Can individual elements be written? | Mutation TTL scope |
|---|---|---|---|
| Non-frozen `map<K,V>` | One cell per map key | Yes: update individual keys | The elements written by the mutation |
| Non-frozen `set<T>` | One cell per set element | Yes: add/remove elements | Newly written elements |
| Non-frozen `list<T>` | Multiple cells for list elements | Yes: append elements, some positional ops | The elements written by the mutation |
| Non-frozen UDT | One cell per field | Yes: update individual fields | The fields written by the mutation |
| `frozen<collection>` | One cell for the entire collection | Cannot update single elements like non-frozen | The entire frozen cell |
| `frozen<udt>` | One cell for the entire UDT | Cannot update single fields | The entire frozen cell |

**Note:** the table above illustrates the conceptual storage model to clarify TTL and mutation timestamps. Exact cell path, tombstone, and serialization details can vary by collection type and Cassandra version; do not assume identical update syntax across every type.

## 3. Declaring a Test Table for Collections and UDTs

Practice in a **test keyspace** selected with `USE <keyspace>;`. The following commands use fresh type/table names; if they already exist with a different schema, use different names rather than assuming `IF NOT EXISTS` alters an old schema.

### Create the UDT

```sql
CREATE TYPE IF NOT EXISTS address_udt (
    street text,
    city text,
    country text
);
```

### Create a Table with Both Frozen and Non-Frozen Columns

```sql
CREATE TABLE IF NOT EXISTS ttl_shapes_by_id (
    profile_id uuid PRIMARY KEY,
    attributes map<text, text>,
    labels set<text>,
    milestones list<text>,
    contact address_udt,
    frozen_contact frozen<address_udt>,
    frozen_attributes frozen<map<text, text>>,
    note text
);
```

In this table:

- `attributes`, `labels`, and `milestones` are **non-frozen** collections to demonstrate elements with independent lifecycles.
- `contact` is a **non-frozen** UDT, allowing single-field updates.
- `frozen_contact` and `frozen_attributes` are values stored as **a single cell**, convenient for reading/writing the whole object atomically but without independent per-element operations like non-frozen types.
- `note` is a regular scalar column to keep live data in the row and serve as an independent observation anchor.

Insert an initial row:

```sql
INSERT INTO ttl_shapes_by_id (profile_id, note)
VALUES (
    99999999-9999-4999-8999-999999999999,
    'row kept for demonstrations'
);
```

The following sections share the UUID above and assume execution **in the order presented**, fast enough that short TTLs have not yet expired before you read back. When testing independently or re-running, use a new UUID so leftover timestamps/tombstones do not interfere.

## 4. Non-Frozen `map`: Different TTLs per Key

A non-frozen map is stored as elements associated with each **map key**. If keys are written in different mutations with different TTLs, their expiration times can differ.

### 4.1. Writing a Long-Lived Key and a Temporary Key

```sql
-- Key tier lives 1 hour from this update.
UPDATE ttl_shapes_by_id
USING TTL 3600
SET attributes['tier'] = 'pro'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

-- Key otp_hint lives only 60 seconds from its separate update.
UPDATE ttl_shapes_by_id
USING TTL 60
SET attributes['otp_hint'] = 'expires-soon'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT attributes, note
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Right after both statements, `attributes` may contain:

```text
{'tier': 'pro', 'otp_hint': 'expires-soon'}
```

After 60 seconds have passed, `otp_hint` is no longer a live element of the map, while `tier` can still persist until its 3,600 seconds expire. **It is one logical map, yet two elements have different TTLs.**

### 4.2. Updating a Single Key

```sql
-- Rewrite key tier as a version with no TTL.
UPDATE ttl_shapes_by_id
USING TTL 0
SET attributes['tier'] = 'enterprise'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

If the new mutation wins by **write timestamp**, `tier` takes the new value and will not expire via TTL. Doing this **does not extend** `otp_hint`. Similarly, rewriting `otp_hint` with a new TTL only changes the TTL of that written element.

**Practice warning:** `USING TTL 0` means no TTL on the newly written value. It is not a way to delete an element. Deleting a map key is done with the corresponding update/delete operation:

```sql
DELETE attributes['otp_hint']
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Deletion creates an element-scoped tombstone so stale replicas cannot bring back the deleted key during reconciliation.

### 4.3. Writing Multiple Keys in the Same Mutation

```sql
UPDATE ttl_shapes_by_id
USING TTL 120
SET attributes = attributes + {
    'region': 'apac',
    'channel': 'mobile'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Both keys written in the same mutation generally receive the write timestamp/TTL of that mutation. However, other pre-existing keys in the map **do not have their TTL reset** merely because two new keys were added.

## 5. Non-Frozen `set`: Per-Element Lifecycle

With a non-frozen `set<text>`, each element is represented by data that Cassandra can reconcile individually. Two elements added by two mutations with different TTLs can expire at different times.

```sql
UPDATE ttl_shapes_by_id
USING TTL 300
SET labels = labels + {'subscribed'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

UPDATE ttl_shapes_by_id
USING TTL 30
SET labels = labels + {'currently-online'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT labels
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Right after writing, both `subscribed` and `currently-online` are visible. After the 30-second TTL, `currently-online` expires while `subscribed` can remain alive.

If a set element **already exists**, adding the same element again can produce a new mutation for that element's cell; if the mutation wins, the TTL/timestamp metadata of that element is updated. Consequently, poorly managed retries can extend TTL unexpectedly.

To delete a specific set element:

```sql
UPDATE ttl_shapes_by_id
SET labels = labels - {'currently-online'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Do not think of set subtraction as "waiting for TTL expiration"; it is a deletion that creates a tombstone. Also avoid using a set as an event occurrence counter: sets **do not hold duplicate elements**, so they cannot record repeated occurrences.

## 6. Non-Frozen `list`: Elements Can Expire Individually, Making Indices Unstable

A non-frozen `list<text>` can store elements in separate cells. A list **appended** across multiple mutations with different TTLs can lose elements piecemeal as they expire.

```sql
UPDATE ttl_shapes_by_id
USING TTL 30
SET milestones = milestones + ['started']
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

UPDATE ttl_shapes_by_id
USING TTL 300
SET milestones = milestones + ['ready']
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT milestones
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Right after writing, the list can show `['started', 'ready']`; once `started` expires, the observed list may only show `['ready']`. Different expiration times cause **the index positions of surviving elements to shift** in read results.

This is one reason not to use a Cassandra list as a strictly ordered work queue, or rely on `milestones[0]` as a stable identifier under concurrent writes/TTL. Certain positional list edits/deletes also incur read-before-write overhead and surprising behavior under concurrent writes.

For event data that genuinely needs history, it is usually better to store **each event as a row** with a time-based clustering key or managed sequence, rather than stuffing an entire history into a large list.

## 7. Non-Frozen UDT: TTL per Field

A **User-Defined Type (UDT)** groups closely related attributes into one data type. If a UDT column is **non-frozen**, Cassandra can store each field as a separate cell. Updating one field does not automatically refresh the TTL of every other field.

### 7.1. Initial Full UDT Write

```sql
UPDATE ttl_shapes_by_id
SET contact = {
    street: '12 Nguyen Trai',
    city: 'Ha Noi',
    country: 'VN'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT contact
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

In this test table with no default TTL, the newly written fields on `contact` do not expire automatically because this mutation has no `USING TTL`.

### 7.2. Setting a Specific TTL for the `city` Field

```sql
UPDATE ttl_shapes_by_id
USING TTL 60
SET contact.city = 'Da Nang'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT contact
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Right after writing, the logical result is roughly:

```text
{street: '12 Nguyen Trai', city: 'Da Nang', country: 'VN'}
```

After 60 seconds, **the `city` field can become `null` or no longer have a live value** in the returned object; `street` and `country` do not automatically expire because the operation above only touched `city`. To keep a UDT valid for business rules, the application must handle **missing fields** in non-frozen UDTs with varying TTLs.

### 7.3. Assigning the Entire UDT

```sql
UPDATE ttl_shapes_by_id
USING TTL 180
SET contact = {
    street: '5 Le Loi',
    city: 'Hue',
    country: 'VN'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

This assigns **the entire UDT value**, unlike `SET contact.city = ...`. Cassandra must handle any old fields omitted from the replacement value according to UDT and tombstone rules; newly written fields get the TTL of this mutation. When business logic only wants to change `city`, use field-level syntax on a non-frozen UDT to avoid rewriting unrelated fields.

## 8. `frozen<map>` and `frozen<UDT>`: TTL for the Whole Object

**Frozen** turns a collection or UDT value into **a single cell**. This changes both how updates work and how TTL applies.

### 8.1. Frozen Map

```sql
UPDATE ttl_shapes_by_id
USING TTL 90
SET frozen_attributes = {
    'locale': 'vi',
    'tier': 'pro'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT frozen_attributes
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

`frozen_attributes` is stored intact as a single value. When the 90-second TTL expires, **the entire frozen map** ceases to be live. You cannot make `locale` expire after 30 seconds and `tier` after 90 seconds **by modifying individual entries of the same frozen cell**.

To change one key, the application must **construct a new frozen map value** and rewrite **the entire cell**; the new mutation's timestamp and TTL apply to the entire new value.

### 8.2. Frozen UDT

```sql
UPDATE ttl_shapes_by_id
USING TTL 120
SET frozen_contact = {
    street: '1 Bach Dang',
    city: 'Da Nang',
    country: 'VN'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT frozen_contact
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

All of `frozen_contact` lives as **one cell** with a 120-second TTL; you cannot write `SET frozen_contact.city = ...` as with a non-frozen UDT. To update `city`, rebuild the entire UDT value and overwrite the single frozen cell.

### Choosing `frozen` Based on Business Requirements

| Requirement | Option to consider |
|---|---|
| Each UDT field/map key has a different lifetime | Non-frozen, update the specific element |
| All components must expire together | Frozen, write and expire the whole value |
| Frequent updates to one map key | Non-frozen map or a dedicated table keyed by entry |
| Preserve an immutable object snapshot | Frozen UDT/map fits better |
| Collection could grow very large | Consider a **row-per-element** model, bounding partition and read/write size |

**Cassandra does not convert non-frozen values to frozen at query time.** This is a schema definition choice; design and test the corresponding update path up front.

## 9. How Table Default TTL, `USING TTL`, and `TTL 0` Apply

In addition to `USING TTL N` on mutations, Cassandra supports `default_time_to_live` at the table level. **Each cell written by a mutation** picks up its TTL according to that mutation's policy at write time:

| Table default TTL | Mutation | Effect on collection/UDT |
|---|---|---|
| `0` (no default) | No `USING TTL` | Newly written elements/cells have no TTL |
| `300` | No `USING TTL` | Newly written elements/cells get the default ~300 seconds |
| `300` | `USING TTL 60` | Newly written elements/cells get a 60-second TTL |
| `300` | `USING TTL 0` | Newly written cells have no TTL |
| Any | Write one field of a non-frozen UDT | Other fields' TTLs do not change automatically |
| Any | Rewrite a frozen UDT/map | The entire frozen cell gets the new version's TTL |

Example with another table that has a default TTL:

```sql
CREATE TABLE IF NOT EXISTS ttl_collection_default_by_id (
    id uuid PRIMARY KEY,
    attrs map<text, text>,
    snapshot frozen<map<text, text>>,
    note text
) WITH default_time_to_live = 600;

INSERT INTO ttl_collection_default_by_id (id, attrs, note)
VALUES (
    aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa,
    {'source': 'api', 'kind': 'temporary'},
    'default TTL demo'
);

-- Key pinned is a newly written element with no TTL.
UPDATE ttl_collection_default_by_id
USING TTL 0
SET attrs['pinned'] = 'true'
WHERE id = aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa;

-- Frozen snapshot lives 120 seconds as a single cell.
UPDATE ttl_collection_default_by_id
USING TTL 120
SET snapshot = {'source': 'api', 'kind': 'temporary'}
WHERE id = aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa;
```

Roughly 600 seconds after the `INSERT`, the `source`/`kind` entries written under the default will have expired. The `pinned` key written with `USING TTL 0` does not expire via TTL, and the frozen `snapshot` expires roughly 120 seconds after its mutation. A table having a default TTL **does not mean every component in the same row always expires simultaneously**.

When `ALTER TABLE ... WITH default_time_to_live = ...` changes the default, existing cells/elements that already have TTLs are not bulk-rewritten by Cassandra. Only **subsequent mutations** use the new default if no explicit TTL is given.

## 10. Replacing an Entire Collection vs. Adding/Updating One Element

This is an easy place to introduce hard-to-diagnose data bugs. Consider a non-frozen map containing `tier` and `locale`:

```sql
-- Update a single key (mutation touches only that element).
UPDATE ttl_shapes_by_id
USING TTL 60
SET attributes['locale'] = 'en'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Contrast that with replacing **the entire map value**:

```sql
-- Replaces the whole map without carrying old keys into the new value.
UPDATE ttl_shapes_by_id
USING TTL 600
SET attributes = {'tier': 'basic'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

The second statement has **collection replacement** semantics: Cassandra handles deleting elements belonging to the old value and writing the new elements. Keys such as `locale` disappear even if their prior TTL still had remaining lifetime. Never describe this operation as "just editing the `tier` key."

Similarly:

- Assigning an entire non-frozen UDT differs from updating a single field.
- For frozen collections/UDTs, **every update replaces the entire cell**.
- For sets and lists, element-addition operators (`+`) differ from replacing the entire collection with a new literal.

**Operational consequence:** full-collection replacements or broad deletes can generate tombstones; very large collections with frequent updates and short TTLs increase compaction/read pressure. When individual elements need independent lifecycles/queries and unbounded growth, consider a table storing one item per row.

## 11. Last-Write-Wins, Tombstones, and TTL on Complex Cells

TTL does not decide which version wins when two writers conflict. Cassandra still reconciles using **mutation timestamps** in **microseconds** and the relevant tombstone rules.

Representative scenarios:

| Write contention | Expected outcome |
|---|---|
| Two writers edit the **same map key** | Compare write timestamp/tombstone of that element |
| Two writers edit **different map keys** | Both can coexist, each key keeping its own metadata |
| Two writers edit **different non-frozen UDT fields** | Each field can receive its value and TTL from its respective mutation |
| Two writers replace the **same frozen UDT** | Compare versions of **one frozen cell**; one version wins entirely |
| Delete a key, then rewrite that key with a timestamp lower than the tombstone | Older value is shadowed by the tombstone |
| Replace an entire non-frozen collection | Must account for collection-level tombstones and element timestamps |

Example of heterogeneous TTLs inside one map:

```text
attributes['tier']   = 'pro'        @ timestamp 100, TTL 3600
attributes['locale'] = 'vi'         @ timestamp 200, TTL  120
attributes['otp']    = 'temporary'  @ timestamp 300, TTL   30

After otp expires, tier and locale can still remain alive.
If another writer rewrites otp with timestamp 250, it can
lose to the expired tombstone/metadata at timestamp 300.
```

**Clock skew** causes problems here too: a client with a far-future timestamp can make later updates to the same key/field lose under LWW. Using TTL does not fix clock skew, and raising consistency level does not change timestamp arbitration rules.

## 12. Reading and Inspecting Collection/UDT TTLs

For regular scalar columns, you can read:

```sql
SELECT note, writetime(note), ttl(note)
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

`writetime(note)` returns the write timestamp metadata in **microseconds**, and `ttl(note)` returns **remaining seconds** if the `note` cell has a TTL. However, **do not assume you can call `ttl(attributes)` or `writetime(contact)` to retrieve all timestamps/TTLs across every element of a non-frozen collection/UDT**. One logical column can hold many cells with distinct metadata; how CQL functions and selectors behave on complex types also carries constraints by data type and Cassandra version.

To observe at the application level:

1. **Read the current value** by partition key: `SELECT attributes, labels, milestones, contact, frozen_contact ...`.
2. **Log the mutation path:** which element/field was written, the request's TTL, mutation timestamp if client-supplied, event ID, and retry count.
3. **Read again after a short TTL in a test environment**, checking that keys/fields/elements remain live as expected.
4. When you must inspect **specific cell-level TTLs and tombstones**, use the admin/SSTable tools for your Cassandra version under a controlled operational procedure.

```sql
SELECT attributes, labels, milestones,
       contact, frozen_contact, frozen_attributes, note
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Never treat an empty collection as sole proof to distinguish **never written**, **deleted**, and **TTL expired**. Cross-check request history; depending on type, version, and client formatting, an empty or expired collection may be represented differently.

## 13. Java Application: Writing a Map Key and a UDT Field with TTL

In Java using **Apache/DataStax Cassandra Java Driver 4.x**, prepared statements let you update a single element/field without rewriting the entire collection or UDT. TTL is bound in **seconds**; remember error handling and retry logic in real systems.

```java
import java.util.Map;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ProfileTtlRepository {
    private final CqlSession session;
    private final PreparedStatement updateLocale;
    private final PreparedStatement updateCity;
    private final PreparedStatement readProfile;

    public ProfileTtlRepository(CqlSession session) {
        this.session = session;
        this.updateLocale = session.prepare(
            "UPDATE ttl_shapes_by_id USING TTL ? " +
            "SET attributes['locale'] = ? WHERE profile_id = ?"
        );
        this.updateCity = session.prepare(
            "UPDATE ttl_shapes_by_id USING TTL ? " +
            "SET contact.city = ? WHERE profile_id = ?"
        );
        this.readProfile = session.prepare(
            "SELECT attributes, contact FROM ttl_shapes_by_id " +
            "WHERE profile_id = ?"
        );
    }

    public void setLocale(UUID id, String locale, int ttlSeconds) {
        requirePositiveTtl(ttlSeconds);
        session.execute(updateLocale.bind(ttlSeconds, locale, id));
    }

    public void setCity(UUID id, String city, int ttlSeconds) {
        requirePositiveTtl(ttlSeconds);
        session.execute(updateCity.bind(ttlSeconds, city, id));
    }

    public Map<String, String> getAttributes(UUID id) {
        Row row = session.execute(readProfile.bind(id)).one();
        return row == null ? null
            : row.getMap("attributes", String.class, String.class);
    }

    private static void requirePositiveTtl(int ttlSeconds) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }
    }
}
```

`setLocale` applies TTL to the newly written **`locale` key**; `setCity` applies TTL to the **`city` field** of the non-frozen UDT. Neither method touches other components, so their TTLs are not intentionally reset. The code assumes the table/UDT already exist and `CqlSession` is connected to the proper keyspace.

On read, an expired map key or UDT field may no longer be present. Java code must handle **missing map keys, `null` fields, and `null` rows** rather than assuming every object is always complete. To write a frozen UDT, bind **the entire UDT value** using the driver codec/API and attach TTL to that frozen cell.

If lifetime has exact business meaning (e.g., OTPs or session tokens), also store an explicit expiration timestamp from a **trusted time source** and check business validity; Cassandra TTL does not replace single-use checks or LWT/compare-and-set.

## 14. Choosing a Data Model Around Lifecycle and Queries

Collections are convenient for reading a small group of attributes within one partition. However, collections are unsuitable when element counts grow unboundedly, individual elements must be queried/filtered independently, or items are frequently updated/deleted with differing TTLs.

Example business requirement needing to query a user's notifications by day and newest time:

```sql
CREATE TABLE IF NOT EXISTS notifications_by_account_day (
    account_id uuid,
    notification_day date,
    event_time timeuuid,
    payload text,
    PRIMARY KEY ((account_id, notification_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

-- Each event is a separate row and can receive its own TTL on INSERT.
INSERT INTO notifications_by_account_day (
    account_id, notification_day, event_time, payload
) VALUES (
    22222222-8888-4888-8888-222222222222,
    '2026-11-21',
    now(),
    'New event'
)
USING TTL 3600;
```

Each event row has its own clustering key; TTL attaches to the new cells in that row rather than managing per-element TTLs across thousands of entries in one list/map. For high-volume streams, choose an appropriate **time bucket** so partitions do not grow too large.

| Business requirement | Design worth considering |
|---|---|
| Small group of attributes, keys updated independently | Non-frozen map |
| UDT with fields changing and expiring independently | Non-frozen UDT, handling missing fields |
| Consistent snapshot as one value, expiring together | Frozen UDT or frozen collection |
| Event history with many elements, queried by time | Event-per-row table with clustering key |
| Elements needing lookup/deletion across multiple query paths | Dedicated tables designed per query |

**Never use mutation timestamps as an implicit clustering key.** If you need to query in event order, store the business timestamp or sequence as key data. Mutation timestamps serve cell-level LWW, while TTL governs cell version lifetime.

## 15. Operations: Tombstones, Compaction, Repair, and Replication

Expired TTL cells are treated like deleted data; Cassandra needs tombstone/expiration metadata so unsynchronized replicas do not resurrect stale data. In a map or UDT with many cells, elements can expire at many different times, creating extra **tombstones and read/compaction overhead**.

- **Replication factor** determines how many replicas store the partition; **consistency levels** such as `ONE`, `QUORUM`, `ALL` govern read/write quorum requirements, without turning per-element TTLs into a single shared TTL.
- **Repair** brings replicas into convergence. If tombstones are purged unsafely while another replica still holds stale data, there is a risk of **zombie data**.
- **Compaction** merges SSTables and can purge expired data/tombstones when safe; TTL expiration does not immediately free disk space.
- **Clock skew** across hosts generating mutation timestamps or nodes evaluating expiration can affect read outcomes, LWW order, and perceived remaining lifetime.
- **Full-collection replacements** or constant churn of adding/removing elements can increase tombstones. Large collections also add overhead when clients must read/write an entire frozen value.

In production, monitor disk usage, tombstones, read latency, compaction rate, repair health, and partition sizes. Never lower `gc_grace_seconds` or delete SSTables just to shorten TTL cleanup time: those changes directly affect replication safety.

## 16. Common Bugs and How to Diagnose Them

| Symptom | Possible explanation | How to check |
|---|---|---|
| One map key disappears while others remain | Keys were written with different TTLs | Inspect `UPDATE map['key']` history and each mutation's TTL |
| One UDT field turns `null` while others stay | Non-frozen UDT, TTL per field | Check schema and `UPDATE udt.field` statements |
| Entire frozen map vanishes at once | Frozen map is a single cell with one TTL | Check the latest write to the frozen cell |
| Updating one key wiped other keys | Likely **replaced the entire map** instead of editing one entry | Compare `SET map = {...}` vs. `SET map['k'] = ...` |
| List loses elements, shifting indices | Element cells expired or were deleted | Do not rely on list index as a stable identifier |
| New write happened, yet old element still wins | Lower mutation timestamp or newer tombstone | Check timestamp source, retries, and clock skew |
| Wrote with TTL, yet read shows no TTL | Mutation lost LWW, or a newer version had `TTL 0` | Trace timestamps/TTLs across mutations |
| Expired data still consumes disk space | Tombstones/data awaiting safe compaction | Inspect SSTables, compaction, repair, and grace settings |

An effective diagnostic workflow:

1. Verify the **exact schema**: whether columns are frozen or non-frozen, collection kind, UDT fields, and whether the table sets `default_time_to_live`.
2. Determine the **mutation scope**: full collection/UDT replacement or single key/element/field.
3. Check the **assigned TTL and timestamp** on the request; confirm TTL is in seconds and write timestamp is in microseconds.
4. Query the exact **partition key**, read live values, and compare against operational logs and expected timelines.
5. If replica/tombstone issues are suspected, cross-check CL, node health, repair status, and use Cassandra tools suited to your environment.

## 17. Self-Check Exercises

**Question 1.** In a non-frozen map, `['a']` is written with a 30-second TTL and `['b']` with a 300-second TTL. After 45 seconds, what is expected?

**Answer:** Key `a` has expired and is no longer returned in reads, while `b` can still remain live. Both keys carry separate TTL metadata.

**Question 2.** A `frozen<map<text,text>>` with two keys is written using `UPDATE ... USING TTL 60`. Can you make one key expire at 30 seconds just by editing that single key?

**Answer:** No. A frozen map is one cell. Changing data or TTL requires rewriting **the entire frozen cell** or changing the model to non-frozen/a separate table.

**Question 3.** A non-frozen UDT has `street`, `city`, and `country`. Does `UPDATE ... USING TTL 30 SET contact.city = 'Hue'` extend `street`'s TTL?

**Answer:** No. The mutation updates only the `city` field; other fields keep the metadata of their respective versions.

**Question 4.** A list contains `['a','b']`, and element `a` expires before `b`. Can you assume index 0 is always `a`?

**Answer:** No. Once `a` is no longer live, the observed list can contain only `b`, shifting indices.

**Question 5.** A table has `default_time_to_live = 600`. Does adding a set element with `USING TTL 0` remove TTL from the entire set?

**Answer:** No. Only the cell/element written by that mutation gets TTL 0; existing elements retain their own metadata.

**Question 6.** When replacing `attributes = {'tier': 'basic'}`, why can `locale` disappear even though its TTL had time left?

**Answer:** That is a **full collection replacement** operation with semantics that delete prior elements not included in the new value, not merely an update to the `tier` key.

**Question 7.** Can `ttl(attributes)` be used to retrieve a full table of TTLs per map key?

**Answer:** Do not treat it as an API for inspecting per-element metadata. Non-frozen maps contain multiple cells with distinct TTLs; check your Cassandra version's capabilities and rely on mutation history/appropriate diagnostic tools.

**Question 8.** A collection is huge and needs queries for the newest elements over time. Should you keep appending to a list or design a different table?

**Answer:** Consider **one row per event**, partitioned by entity key + time bucket with a time/sequence clustering key. Query-driven modeling is usually far better for unbounded growth.

---

**Key takeaway:** For **non-frozen collections/UDTs**, Cassandra can store **individual elements or fields as separate cells**, so components written in different mutations can carry **different TTLs and mutation timestamps**. For **frozen collections/UDTs**, the entire value is **one cell**, written and expired as a single unit. `USING TTL` applies to the components/cells touched by the mutation, interacting with `default_time_to_live` and last-write-wins rules. Understanding storage layout is essential to predicting when each value expires, avoiding unnecessary tombstones, and designing Cassandra tables around queries.
