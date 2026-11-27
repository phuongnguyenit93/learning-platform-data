# Updating Collections and Element-Level Operations in Apache Cassandra

In Apache Cassandra, a column can hold a **collection**: a `map` (key–value mapping), a `set` (unique elements), or a `list` (ordered sequence of elements). CQL allows **replacing the entire collection** or **modifying part of the contents** of a non-`frozen` collection. Choosing the wrong operation can wipe out existing elements, generate excessive tombstones, or cause conflicts when multiple clients write concurrently.

This lesson belongs to the **CQL Writes and Deletes** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. In Cassandra, the **partition key** determines the partition and replicas storing the data, while the **full primary key** identifies the target row. Collections still follow distributed write mechanics, timestamps, TTL, and consistency levels. Therefore, designing collection updates requires considering both CQL semantics and how the Java application executes them.

After this lesson, you will be able to:

- Distinguish `map<k,v>`, `set<t>`, and `list<t>`, and know when to use each.
- Write `UPDATE` statements to replace an entire collection, add/remove elements, and update elements by key or position.
- Explain the difference between **omitting a column**, **assigning NULL**, **assigning a new collection**, and **editing individual elements**.
- Recognize limitations of `frozen` collections, contention risks with `list`, and tombstone/TTL impacts.
- Use Java Driver prepared statements to modify collections safely.

## 1. Data model and test table

Suppose a user profile service needs to store a small set of preferences, tags, and a list of recent steps. The `demo` keyspace is assumed to exist:

```sql
CREATE TABLE demo.user_collections_by_id (
    user_id       uuid PRIMARY KEY,
    attributes    map<text, text>,
    tags          set<text>,
    recent_steps  list<text>,
    version       int,
    updated_at    timestamp
);
```

In this table, `user_id` is both the **partition key** and the **full primary key**. Each `UPDATE ... WHERE user_id = ...` locates one logical row; the three collections are regular columns, not primary key components.

Initialize data:

```sql
INSERT INTO demo.user_collections_by_id (
    user_id, attributes, tags, recent_steps, version
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    {'theme': 'light', 'locale': 'vi-VN'},
    {'trial', 'newsletter'},
    ['login', 'browse'],
    1
);

SELECT attributes, tags, recent_steps, version
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Expected result (the display order of `map` and `set` carries no business meaning):

| Column | Initial value | Meaning |
| --- | --- | --- |
| `attributes` | `{'theme': 'light', 'locale': 'vi-VN'}` | Look up values by configuration key |
| `tags` | `{'trial', 'newsletter'}` | Unique tags with no fixed order |
| `recent_steps` | `['login', 'browse']` | Ordered list that can contain duplicate elements |
| `version` | `1` | Regular column used to illustrate conditional writes |

The examples in sections 2–5 **independently illustrate how to write statements**; if you run multiple statements sequentially, the state before each statement reflects all previously executed statements. The hands-on lab at the end provides a clear command sequence and expected results.

### Choosing a collection type for your requirements

| Type | Characteristics | Typical access/update pattern |
| --- | --- | --- |
| `map<text,text>` | Unique keys, one value per key | `attributes['theme'] = 'dark'` |
| `set<text>` | Unique elements, not position-based | `tags = tags + {'vip'}` |
| `list<text>` | Ordered and can hold duplicate values | `recent_steps = recent_steps + ['checkout']`; `recent_steps[0] = 'open'` |

Collections should be **small and strictly bounded**. An ever-growing event stream over time is not suited for stuffing into a large `list` on a single row. Instead, use a query-driven table with a partition key and clustering columns—for instance, partitioned by user + day with events ordered by timestamp.

## 2. Assigning an entire collection vs. partial updates

Directly assigning a collection via `SET column = <collection literal>` means **replacing the contents of the collection column**:

```sql
UPDATE demo.user_collections_by_id
SET attributes = {'theme': 'dark'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

If before the statement the map held `{'theme': 'light', 'locale': 'vi-VN'}`, after the new assignment it contains only `{'theme': 'dark'}`; the `'locale'` key is removed. In a non-`frozen` collection, a full replacement is typically represented by a collection-range tombstone plus the new elements.

The same holds for `set` and `list`:

```sql
-- Replaces the entire set; old tags not listed will disappear.
UPDATE demo.user_collections_by_id
SET tags = {'vip'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Replaces the entire list with two elements in the new order.
UPDATE demo.user_collections_by_id
SET recent_steps = ['open', 'checkout']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

**Rule:** `SET tags = {'vip'}` is a **replace**, whereas `SET tags = tags + {'vip'}` **appends to the existing collection**. Do not use replace syntax for an endpoint that only intends to "add a tag."

### What happens when a collection column is omitted?

```sql
UPDATE demo.user_collections_by_id
SET version = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

This statement writes only `version`; it **does not modify** `attributes`, `tags`, or `recent_steps` because they are absent from `SET`. An omitted field differs from a new empty collection or `NULL`. This rule also applies to regular column-list `INSERT` upserts.

## 3. Updating a map: adding, editing, and deleting a key

For a **non-frozen** `map`, Cassandra lets you update the value at a single key without resending the entire map.

### 3.1. Assigning or adding a key–value pair

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.user_collections_by_id
SET attributes['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

- If `'theme'` already exists, the value at that key is overwritten.
- If `'timezone'` does not exist yet, Cassandra inserts the new key/value pair.
- Other keys in `attributes` **are not deleted by these mutations**.

For instance, starting from `{'theme':'light','locale':'vi-VN'}`, the two statements above produce a map with `theme = dark`, `locale = vi-VN`, and `timezone = Asia/Ho_Chi_Minh`.

### 3.2. Adding multiple pairs to an existing map

```sql
UPDATE demo.user_collections_by_id
SET attributes = attributes + {'theme': 'dark', 'lang': 'vi'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

The `+` operator on a map **adds or updates the keys listed** in the right-hand map; it does not remove other keys. If `theme` already exists, its value is overwritten; `lang` is added if absent.

Comparison:

| CQL | `theme` | Existing `locale` | `lang` |
| --- | --- | --- | --- |
| `SET attributes = {'theme':'dark', 'lang':'vi'}` | Replaced with dark | **Removed from map** | Added |
| `SET attributes = attributes + {'theme':'dark', 'lang':'vi'}` | Replaced with dark | **Preserved** | Added |
| `SET attributes['theme'] = 'dark'` | Replaced with dark | **Preserved** | Unaffected |

### 3.3. Deleting a key from a map

```sql
DELETE attributes['locale']
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

This statement **deletes only the map entry with key `'locale'`**, not the entire `attributes` column. Cassandra writes deletion metadata for that entry so older versions do not reappear on reads.

You can also subtract a set of keys from a map:

```sql
UPDATE demo.user_collections_by_id
SET attributes = attributes - {'locale', 'lang'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

In this expression, the right-hand side is a **set of keys to remove**, not a new map. Removing a key absent from the map does not throw a "key not found" error like out-of-bounds array element deletion might.

### 3.4. NULL and map keys

Do not use `NULL` as a **map key**. To remove the `'theme'` pair, use `DELETE attributes['theme']` or a key-removal update. Assigning `attributes = NULL` expresses the intent to **delete the entire collection**, completely different from deleting a single entry.

Maps work well for **small** preference sets, but if you want to query all users with `theme='dark'`, a map inside a `user_id`-keyed row does not automatically provide an efficient distributed lookup path by that value. Cassandra modeling must start from queries: you may need another table with an appropriate query key.

## 4. Updating a set: adding and removing unique elements

`set<text>` stores a collection of **unique** values with no meaningful ordering or indexing. For non-`frozen` `set`s, Cassandra supports set union and set difference.

### Adding one or more elements

```sql
UPDATE demo.user_collections_by_id
SET tags = tags + {'vip'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.user_collections_by_id
SET tags = tags + {'active', 'newsletter'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

If the initial set is `{'trial','newsletter'}`, adding `'vip'` inserts `'vip'`; the next operation adds `'active'`. Adding `'newsletter'` again does not create a duplicate copy because this is a `set`.

The display order of `tags` in CQL results is not an insertion history. If you need operation ordering, a `set` does not satisfy that requirement.

### Removing one or more elements

```sql
UPDATE demo.user_collections_by_id
SET tags = tags - {'trial'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.user_collections_by_id
SET tags = tags - {'vip', 'active'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Elements not in the subtraction set are unaffected by these two mutations. For a set, there is **no** valid syntax like `tags[0]` to reference the "first" element, because sets are not position-indexed.

### Assigning a new set or NULL

```sql
-- Replaces the entire set with the tags below.
UPDATE demo.user_collections_by_id
SET tags = {'vip'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Deletes the entire collection column value.
UPDATE demo.user_collections_by_id
SET tags = NULL
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Assigning `NULL` requests deleting the collection value; it is not a "skip field" operation. Deleting the whole column can also be written as:

```sql
DELETE tags
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Deletes in Cassandra create tombstones matching the scope of deleted data. If an API only intends to remove `'trial'`, use `tags = tags - {'trial'}` instead of reassigning the whole set from whatever snapshot the client happens to hold.

## 5. Updating a list: positions, appending, prepending, and deleting

`list<text>` stores an **ordered** sequence and allows duplicate values. This introduces operations unavailable on sets, while also making index-based edits sensitive to concurrent writes.

### 5.1. Appending to the end of a list

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps + ['checkout']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Starting from `['login','browse']`, the expected result is `['login','browse','checkout']`.

Multiple elements can be appended at once:

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps + ['pay', 'confirm']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

The new elements are appended to the current list; `list` **does not** deduplicate values automatically.

### 5.2. Prepending to the beginning of a list

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = ['open'] + recent_steps
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Concatenation places a list on the left to prepend elements. Prepending is generally more complex and costly than appending because ordering relative to existing elements must be established. Never use an ever-growing list as an event log or multi-producer queue.

### 5.3. Modifying an element at an index

```sql
-- List indices are 0-based.
UPDATE demo.user_collections_by_id
SET recent_steps[1] = 'search'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

If immediately prior the list was `['login','browse']`, index `1` targets the second element and the expected result is `['login','search']`. Updating by index requires knowing an **existing position**; specifying an out-of-bounds index or an invalid position can result in an error.

### 5.4. Deleting elements by index or by value

```sql
-- Deletes the element currently at index 0.
DELETE recent_steps[0]
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Removes elements with value 'browse' from the list.
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps - ['browse']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

The two statements express different semantics. Deleting by index touches **the element at the specified position when the operation executes**. Deleting by value targets **elements matching that value** in the list, since a list can contain duplicates.

### Why be careful with list indices?

Suppose client A reads `['login','browse']` and intends to update index `1`. Before A writes, client B prepends `'open'` or deletes an element. Index `1` may no longer point to the action A intended. Index-based updates may also require reading list state internally and are ill-suited to high-contention write workloads.

**Recommendation:** use lists only for short, low-contention sequences where ordering matters. If you need to reliably update/delete events by ID, designing a table with **an event ID or timestamp as a clustering key** is usually far better—for instance, `events_by_user_day` with partition key `(user_id, event_day)` and clustering key `event_id` or `event_time`, rather than an unbounded list in a single row.

## 6. Frozen collections and element-level update limits

`frozen` changes how Cassandra treats a collection: the entire collection is handled as **a single monolithic value**. Reading/writing the whole value is valid, but you **cannot** use element-level modification operations as with non-`frozen` collections.

Example table with a frozen map:

```sql
CREATE TABLE demo.user_frozen_profile_by_id (
    user_id uuid PRIMARY KEY,
    settings frozen<map<text, text>>
);

INSERT INTO demo.user_frozen_profile_by_id (user_id, settings)
VALUES (
    22222222-2222-4222-8222-222222222222,
    {'theme': 'light', 'locale': 'vi-VN'}
);
```

Writing the entire frozen map:

```sql
UPDATE demo.user_frozen_profile_by_id
SET settings = {'theme': 'dark', 'locale': 'vi-VN'}
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Not supported:

```sql
-- INVALID: frozen maps do not support direct element updates.
UPDATE demo.user_frozen_profile_by_id
SET settings['theme'] = 'dark'
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

To change one field in a `frozen` map, the application typically must build a **complete new map value** and reassign it. If two clients read the old version and both rewrite the whole map, one update can overwrite unrelated entries just modified by the other client. Under concurrent write loads, consider modeling regular columns, a non-frozen map, or appropriate LWT conditions.

| Operation | `map<text,text>` | `frozen<map<text,text>>` |
| --- | --- | --- |
| Assign entire map | Yes | Yes |
| `map_col['k'] = 'v'` | Yes | No |
| `DELETE map_col['k']` | Yes | No |
| Assign `NULL` to delete whole column | Yes | Yes |
| Typical reconciliation unit | Per element plus collection tombstones | Monolithic collection value |

Do not choose `frozen` simply because the name sounds like "rarely changes": it is a **storage model and mutation-scope** decision that must match your application's access patterns.

## 7. NULL, UNSET, tombstones, and TTL for collections

Non-`frozen` collections are typically stored by Cassandra with **element-level** metadata rather than a single blob representing the whole value. This enables partial updates, yet also affects tombstones and TTLs.

### 7.1. Omitting the column, assigning NULL, and assigning a new collection

Consider a row that already has `attributes`, `tags`, and `recent_steps`:

| Mutation | Effect on collection |
| --- | --- |
| `SET version = 3`, omitting `tags` | Does not rewrite `tags` |
| `SET tags = tags + {'vip'}` | Adds element, preserves other elements |
| `SET tags = {'vip'}` | Replaces entire set; unmentioned old elements are removed |
| `SET tags = NULL` | Deletes the collection column value |
| Prepared statement with marker `tags = UNSET` | Skips writing the `tags` column |

`NULL` **is not UNSET**. Assigning `NULL` writes a deletion marker for the column; `UNSET` is a prepared-statement parameter state that avoids generating a mutation for that column. When a Java application receives a JSON request containing only `attributes.theme`, it must never automatically bind `tags = NULL` simply because the client omitted tags.

### 7.2. Element-level and whole-collection tombstones

Deleting `attributes['locale']` creates deletion metadata for that map entry, whereas reassigning the whole map or deleting the entire column marks a broader range of prior data as deleted. Deleting does not mean Cassandra instantly removes every old record from SSTables across all replicas.

In a distributed system, a replica may temporarily miss a delete mutation. Timestamped **tombstones** allow Cassandra to shadow stale values during reads and reconciliation. Repair helps replicas converge; compaction can purge tombstones and stale data once safety conditions are satisfied. Generating excessive tombstones (such as repeatedly replacing a large collection) can make reads heavy and increase compaction pressure.

### 7.3. TTL when writing elements

TTL is specified in seconds:

```sql
UPDATE demo.user_collections_by_id USING TTL 600
SET attributes['temporary_status'] = 'online'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

For a non-`frozen` collection, writing an element with a TTL causes **the newly written element** to expire after 600 seconds; other map entries do not inherit this write's TTL. Similarly, `UPDATE ... USING TTL ... SET tags = tags + {'temporary'}` applies to the added element; existing elements do not get their TTLs extended. A **full-collection reassignment** has a broader write scope and can affect the TTL of many elements.

Do not treat TTL as an "instant data-file cleaner": upon expiration, values are no longer read as live data, and Cassandra handles expired cells during storage and compaction.

### 7.4. Write timestamps and competing elements

A non-`frozen` map can receive two mutations to two different keys:

```text
Client A writes attributes['theme']    = 'dark'
Client B writes attributes['timezone'] = 'Asia/Ho_Chi_Minh'
```

If both writes succeed, values at **two distinct map keys** can coexist because they do not contend on the same element. However, if two clients both write `attributes['theme']`, the winner depends on the element's **timestamp** and Cassandra's reconciliation rules. A **full-map replace** racing with a single-element edit can also wipe or shadow unexpected values.

Standard collection updates do not verify previously read state. If you must enforce "update only while profile version is still 1," use an appropriate condition such as a lightweight transaction (LWT):

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'dark',
    version = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
```

The result includes `[applied]` so the application knows whether the condition held. Conditional updates incur higher cost and latency than unconditional mutations; use LWT only when business invariants truly require it.

### 7.5. Consistency level and retries

Replication keeps the same partition across multiple nodes; consistency level defines acknowledgment thresholds for reads and writes. For example, with replication factor 3, `QUORUM` typically requires two replicas to acknowledge within the applicable quorum scope. However, **QUORUM does not turn read-then-write sequences into conditional transactions**.

When a client receives a timeout, some replicas may already have applied the mutation. Retrying an operation that adds a tag to a `set` with the same value usually does not create duplicates, whereas retrying a `list` append can **append the event a second time**. For operations requiring "exactly-once" semantics, design idempotency or store each event with a deterministic primary key in a dedicated table rather than blindly retrying list appends.

## 8. Java Driver: prepared statements for each operation

With Apache Cassandra Java Driver 4.x, use prepared statements and bind **values**. The following examples assume a valid `CqlSession session` and `UUID userId`; imports are omitted to focus on CQL.

### 8.1. Writing a single map key

```java
PreparedStatement updateAttribute = session.prepare(
    "UPDATE demo.user_collections_by_id " +
    "SET attributes[:attr_key] = :attr_value " +
    "WHERE user_id = :user_id"
);

BoundStatement updateTheme = updateAttribute.boundStatementBuilder()
    .setString("attr_key", "theme")
    .setString("attr_value", "dark")
    .setUuid("user_id", userId)
    .build();

session.execute(updateTheme);
```

`attr_key` and `attr_value` are **bound values**, avoiding CQL string concatenation with keys and values from an HTTP request. If clients are permitted to edit arbitrary map entries, validate against supported keys, enforce length limits, and validate values.

### 8.2. Adding a tag to a set

```java
PreparedStatement addTags = session.prepare(
    "UPDATE demo.user_collections_by_id " +
    "SET tags = tags + :to_add " +
    "WHERE user_id = :user_id"
);

BoundStatement addVip = addTags.boundStatementBuilder()
    .setSet("to_add", java.util.Set.of("vip"), String.class)
    .setUuid("user_id", userId)
    .build();

session.execute(addVip);
```

`setSet(...)` matches CQL `set<text>`. The element-addition statement fits an "add tag" request; only use `SET tags = :new_tags` when the API intends to **replace all tags**.

### 8.3. Appending an element to a list

```java
PreparedStatement appendStep = session.prepare(
    "UPDATE demo.user_collections_by_id " +
    "SET recent_steps = recent_steps + :new_steps " +
    "WHERE user_id = :user_id"
);

BoundStatement append = appendStep.boundStatementBuilder()
    .setList("new_steps", java.util.List.of("checkout"), String.class)
    .setUuid("user_id", userId)
    .build();

session.execute(append);
```

Do not automatically retry a list append after a timeout: resending the same request can append the same element a second time. If an event log cannot tolerate duplicates, a table keyed by event ID is usually a better choice.

### 8.4. Reading collections and inspecting results

```java
PreparedStatement select = session.prepare(
    "SELECT attributes, tags, recent_steps " +
    "FROM demo.user_collections_by_id WHERE user_id = ?"
);

Row row = session.execute(select.bind(userId)).one();
if (row != null) {
    java.util.Map<String, String> attrs =
        row.getMap("attributes", String.class, String.class);
    java.util.Set<String> labels =
        row.getSet("tags", String.class);
    java.util.List<String> steps =
        row.getList("recent_steps", String.class);
    // Handle null and missing values according to the API contract.
}
```

Reading `null` for a collection can mean the column was never written, was deleted, or all its values expired. Do not infer specific business states from a `null` result alone.

### 8.5. Distinguishing a missing collection from JSON null

Example PATCH:

```json
{
  "attributes": {
    "theme": "dark"
  }
}
```

The API contract must clarify whether this is a **single-element merge** or a **full-map replace**. If it is a patch, the backend should emit `attributes['theme'] = :value`; it must not wipe out `locale`. If the client sends:

```json
{
  "attributes": null
}
```

the application must decide whether the API permits deleting the entire map or must return a validation error. **Field absent**, **field present as null**, and **field present as an empty map** are three distinct cases. Jackson `JsonNode.has(...)`/`isNull()` or a field mask helps preserve field presence.

In a prepared statement with markers for whole columns, `UNSET` skips updating the column, whereas binding `NULL` intends to delete the column. When editing only one map entry or set element, use a targeted CQL pattern for that operation to avoid reading and rewriting the whole collection.

## 9. Hands-on lab: updating collections element by element

The following steps use **a dedicated practice UUID** so you can verify state after every mutation. Run sequentially in a test environment against `demo.user_collections_by_id` created in section 1.

### Step 1 — Initialize state

```sql
INSERT INTO demo.user_collections_by_id (
    user_id, attributes, tags, recent_steps, version
)
VALUES (
    33333333-3333-4333-8333-333333333333,
    {'theme': 'light', 'locale': 'vi-VN'},
    {'trial', 'newsletter'},
    ['open', 'browse'],
    1
);

SELECT attributes, tags, recent_steps, version
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Expected:** map has two keys, set has two tags, list has two steps in order, `version = 1`.

### Step 2 — Change one map value and add a new key

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'dark'
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET attributes['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Expected:** `attributes` contains `theme=dark`, `locale=vi-VN`, and `timezone=Asia/Ho_Chi_Minh`. The `locale` key is not removed because both writes edit single map keys.

### Step 3 — Add and remove set tags

```sql
UPDATE demo.user_collections_by_id
SET tags = tags + {'vip'}
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET tags = tags - {'trial'}
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Expected:** the set contains `'newsletter'` and `'vip'`; `'trial'` is removed, with no duplicates.

### Step 4 — Append and modify list elements

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps + ['checkout']
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET recent_steps[1] = 'search'
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Expected:** list is `['open', 'search', 'checkout']`. Index `1` points to the second element of the state after the append.

### Step 5 — Delete map and list elements

```sql
DELETE attributes['locale']
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps - ['search']
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Expected:** the map no longer has `locale`; the list retains `['open', 'checkout']`. Neither element deletion removes the `version` column or the entire collections.

### Step 6 — Update map with a version condition

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'contrast',
    version = 2
WHERE user_id = 33333333-3333-4333-8333-333333333333
IF version = 1;
```

**Expected:** the first time, the condition holds (assuming no concurrent writer), returning `[applied] = true`, `theme = 'contrast'`, and `version = 2`. Running **the exact same** statement again fails `version = 1`, so `[applied] = false` is expected. This is how an application detects a rejected update due to changed prior state.

### Step 7 — Inspect the full row

```sql
SELECT attributes, tags, recent_steps, version
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

| Property | Expected result after step 6 |
| --- | --- |
| `attributes` | `{'theme':'contrast', 'timezone':'Asia/Ho_Chi_Minh'}` |
| `tags` | `{'newsletter','vip'}`; order does not matter |
| `recent_steps` | `['open','checkout']` |
| `version` | `2` |

These results assume no mutations from other clients, no TTLs, and normal write completion.

### Test the difference between "replace entire map" and "edit one element"

Only on disposable practice data, run:

```sql
UPDATE demo.user_collections_by_id
SET attributes = {'theme': 'light'}
WHERE user_id = 33333333-3333-4333-8333-333333333333;

SELECT attributes
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Expected:** `timezone` disappears from the map; this is **whole-collection replacement**, unlike `SET attributes['theme'] = 'light'`. If a client meant only to change the theme and accidentally issued a replace statement, it would lose other preferences.

## 10. Common mistakes

| Statement or assumption | Risk | Fix |
| --- | --- | --- |
| `SET attributes = {'theme':'dark'}` just to edit theme | Wipes remaining map keys | Use `attributes['theme'] = 'dark'` or map merge |
| `SET tags = {'vip'}` to add one tag | Removes existing tags | Use `tags = tags + {'vip'}` |
| Using `tags[0]` | Sets have no meaningful index | Add/remove by element value |
| Updating `recent_steps[1]` from a stale list read | Position may have shifted | Avoid index-based list edits under concurrent writes |
| Using `list` for an unbounded log | Huge collection, expensive reads/writes, retry issues | Design a dedicated event table with clustering keys |
| Editing `settings['theme']` on a frozen map | Element updates unsupported | Assign the whole frozen value or change schema |
| Binding `NULL` for an omitted collection in PATCH | Unwanted data deletion, generates tombstones | Use UNSET or omit column from CQL |
| Retrying list append after timeout | Can append duplicate elements | Use stable event IDs and an idempotent model |
| Repeatedly replacing large collections | Heavy tombstones, higher read and compaction cost | Edit individual elements where suitable; bound collection size |
| Relying on `QUORUM` for atomic read-modify-write | Two clients can still race | Use LWT/`IF` when conditions are needed, or redesign |

## 11. Review questions and design principles

1. **Difference between `SET attributes = {'theme':'dark'}` and `SET attributes['theme'] = 'dark'`?** The first replaces the **entire map**; the second modifies only the `theme` key.
2. **Does adding an existing tag to a set create duplicates?** No; a `set` holds only unique values.
3. **Can you update a `set` by index like a list?** No, because a `set` has no positional order.
4. **How does `DELETE recent_steps[0]` differ from `recent_steps = recent_steps - ['open']`?** The first deletes the element at index `0`; the second removes elements matching `'open'`.
5. **Can you directly edit one element of a `frozen<map<text,text>>`?** No; you must reassign the entire value or choose a non-frozen schema.
6. **Is assigning `tags = NULL` the same as omitting tags from PATCH?** No; `NULL` deletes the collection, whereas omitting or binding UNSET leaves it untouched.
7. **Why shouldn't you append an event to a list and blindly retry on timeout?** Because the prior mutation may already have succeeded, so retrying can record the event a second time.
8. **If two clients edit the map key `theme` concurrently, who wins?** The outcome depends on timestamp-based reconciliation; if the update depends on the previous value, use an appropriate LWT.

When designing Cassandra tables for Java applications, ask: is the collection genuinely **small, bounded, and usually read with the row**? Do we need to query or update **individual elements by a stable identifier**? Are there multiple writers or retries on network failures? If the answer to the latter questions is yes, a separate table with a partition key and clustering keys is likely a better fit than packing every element into a collection.

**Takeaway:** Collection `UPDATE`s operate at two very different scopes: **replacing the entire value** or **operating on individual elements**. `Map` fits key-based edits, `set` fits adding/removing unique values, and `list` fits short ordered sequences—though indices and retries require caution. Clearly separating NULL/UNSET, frozen/non-frozen, TTL/tombstones, and concurrency requirements ensures accurate CQL mutations in distributed Cassandra systems.
