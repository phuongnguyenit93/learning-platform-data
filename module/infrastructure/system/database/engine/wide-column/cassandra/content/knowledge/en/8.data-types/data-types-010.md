# list, set, map, and Choosing Data Structures in Apache Cassandra

In Apache Cassandra, **`list`**, **`set`**, and **`map`** are the three CQL *collection* types, allowing you to store a group of values inside a single column of a row. They differ in **ordering**, **duplicate support**, **per-element lookup**, **mutation semantics**, and **operational cost**. A `list` is not a miniature history table; a `set` is not a tag search index; a `map` does not turn Cassandra into a document database.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The content situates collections within distributed wide-column design: choosing **query-driven partition keys and clustering columns**, reading and writing via CQL, handling retries and conflicts, monitoring tombstones, compaction, repair, replication, and mapping to Java applications. The guiding principle throughout: **collections suit a small, bounded group of elements typically read together; large or unbounded datasets should be modeled across multiple rows**.

## 1. Quick Comparison of list, set, and map

| Criterion | `list<T>` | `set<T>` | `map<K,V>` |
|---|---|---|---|
| Purpose | **Ordered** sequence of elements | Collection of **unique** values | **Key → value** mapping |
| Can contain duplicates? | **Yes** | **No** | Keys are unique; values may duplicate |
| Ordering semantics | Element position/order is meaningful | No business insertion order | No business insertion order |
| Element access | By position/index in supported CQL operations | By member value | By map key |
| Typical mutations | Append/prepend, remove by value, replace by index | Add/remove element | Set/delete entry by key |
| Retrying an add mutation | **Can create duplicates** on append/prepend | Adding the same member does not create a logical duplicate, though concurrency caveats apply | Setting the same key/value does not create duplicate keys, though concurrency caveats apply |
| Good fit for | A few pinned IDs in order, small step lists | Internal tags, small feature sets | Small dynamic-key preferences |
| Do not use for | Unbounded event logs, concurrent timelines | Unbounded member lists | Arbitrary stores with unbounded keys |

**`T`, `K`, `V` are CQL types**: e.g., `list<uuid>`, `set<text>`, `map<text, int>`. Cassandra enforces each component's type rules. Never stuff arbitrary JSON payloads into a collection and treat it as a stable schema.

### 1.1. Choosing a Collection by Business Question

- "User pins **three excerpts in order**" → `list<uuid>` can fit if the count is bounded and concurrent writes are rare.
- "Articles have **unique tags**" → `set<text>`, if the tag set is small and you do not need to search articles cluster-wide solely by that column.
- "Each user has **theme**, **font_size**, **language** as flexible key/value pairs" → `map<text,text>`, if the configuration set is bounded and controlled.
- "Record **every click event** for a user over years" → **multi-row table** using partition buckets and time-based clustering; never use a growing `list`.
- "Find all articles tagged `cassandra`" → a tag access path, an index evaluated for your version/load, or a **separate query table**; `set<text>` inside a row does not solve this on its own.

Separate two questions: **"which structure represents the value?"** and **"which rows does Cassandra retrieve for this query?"** Collections answer the first; partition keys, clustering keys, and indexes answer the second.

## 2. Storage Model: Collections Live Inside a Row

A CQL table can combine multiple data types:

~~~cql
CREATE TABLE reading_state_by_user_article (
    user_id uuid,
    article_id uuid,
    tags set<text>,
    pinned_highlight_ids list<uuid>,
    display_options map<text, text>,
    updated_at timestamp,
    PRIMARY KEY ((user_id, article_id))
);
~~~

Here, `(user_id, article_id)` is a **composite partition key**. Each user–article pair is an independent partition; all three collections are **data columns inside that row**, not separate partitions. The supported query pattern is **reading one user's state for one specific article** when both IDs are known.

~~~cql
INSERT INTO reading_state_by_user_article (
    user_id, article_id, tags, pinned_highlight_ids,
    display_options, updated_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    {'cassandra', 'java'},
    [33333333-3333-4333-8333-333333333333],
    {'theme': 'dark', 'font_size': '16'},
    '2026-11-21T08:00:00Z'
);

SELECT tags, pinned_highlight_ids, display_options, updated_at
FROM reading_state_by_user_article
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND article_id = 22222222-2222-4222-8222-222222222222;
~~~

In the example:

- `{'cassandra', 'java'}` is a **set literal**.
- `[uuid]` is a **list literal**.
- `{'theme': 'dark', 'font_size': '16'}` is a **map literal**.
- Data is fetched using the **full partition key**; Cassandra does not scan every collection across the cluster.

**Do not assume** this table serves "list all articles for a user": querying with only `user_id` and no `article_id` omits part of the partition key. Listing articles by user or time requires a separate read model.

## 3. list<T>: Ordered and Allows Duplicates

### 3.1. List Semantics

`list<T>` represents a **sequence**. Two elements with the exact same value can occupy two different positions:

~~~cql
CREATE TABLE demo_lists_by_id (
    id uuid PRIMARY KEY,
    steps list<text>
);

INSERT INTO demo_lists_by_id (id, steps)
VALUES (
    44444444-4444-4444-8444-444444444444,
    ['DRAFT', 'REVIEW', 'REVIEW', 'PUBLISH']
);
~~~

`REVIEW` appears **twice**; that is not a type error. `list` fits when duplicates carry meaning, such as workflow steps or user-ordered pinned items.

Considerations:

1. List ordering is preserved as part of list semantics.
2. Inserting or deleting at the head shifts the **indices** of trailing elements.
3. An element can appear multiple times; "remove by value" differs from "remove one specific item by unique ID."
4. Lists do not replace **clustering order** for reading multi-row timelines.

### 3.2. CQL Append, Prepend, and Element Removal

~~~cql
-- Append to the end of the list.
UPDATE demo_lists_by_id
SET steps = steps + ['ARCHIVE']
WHERE id = 44444444-4444-4444-8444-444444444444;

-- Prepend to the front of the list.
UPDATE demo_lists_by_id
SET steps = ['START'] + steps
WHERE id = 44444444-4444-4444-8444-444444444444;

-- Remove elements matching a value (not by event ID).
UPDATE demo_lists_by_id
SET steps = steps - ['REVIEW']
WHERE id = 44444444-4444-4444-8444-444444444444;
~~~

Subtracting by value removes matching elements currently in the list. If business logic distinguishes "the first REVIEW" from "the second REVIEW," use **unique IDs per event** instead of storing bare status strings in a list.

CQL also supports **index-based** operations on non-frozen lists, for example:

~~~cql
-- Illustrates index-based update; outcome depends on
-- current element positions and concurrent writes.
UPDATE demo_lists_by_id
SET steps[0] = 'CREATED'
WHERE id = 44444444-4444-4444-8444-444444444444;
~~~

**Never treat a list index as a durable identifier.** Two clients can read a list, both think "element 0" is A, and modify the list concurrently in conflicting ways. Index-based updates or value-based removals can also require reading the existing list state, adding cost and complexity compared to writing a dedicated keyed row.

### 3.3. Retrying Append/Prepend: Risk of Duplicate Additions

Suppose a worker sends:

~~~cql
UPDATE demo_lists_by_id
SET steps = steps + ['SEND_EMAIL']
WHERE id = 44444444-4444-4444-8444-444444444444;
~~~

The client receives a **timeout**, yet some replicas already applied the mutation. If the client retries the exact same append, the list can end up with **two `SEND_EMAIL` elements**, because appending is not an idempotent assignment to a stable element key.

That is why lists should not be used as:

- Job queues requiring **exactly-once per task** execution.
- Audit logs, event streams, or payment histories.
- Action counters.
- Unbounded timelines with concurrent writers and retries.

For those workloads, choose **one row per event with a stable `event_id`** clustered by timestamp or sequence. Never rely on a higher consistency level like `LOCAL_QUORUM` as a substitute for idempotent IDs.

### 3.4. Which Small Lists Fit?

Example: a user selects **up to five highlight IDs** displayed in pinned order. With a strict bound, rare concurrent updates, and retry handling, `list<uuid>` can be concise.

If you need notes, status, author, creation time, and individual edits per highlight, store each highlight as **its own row**, keeping only a small list of pinned IDs if truly needed. When users reorder the list, enforce explicit versioning/concurrency rules so two devices do not overwrite each other's ordering.

## 4. set<T>: Unique Members Without Insertion Order

### 4.1. Set Semantics

`set<T>` holds **each value at most once**. Adding the same value again does not create a duplicate member:

~~~cql
CREATE TABLE demo_tags_by_article (
    article_id uuid PRIMARY KEY,
    tags set<text>
);

INSERT INTO demo_tags_by_article (article_id, tags)
VALUES (
    55555555-5555-4555-8555-555555555555,
    {'java', 'cassandra'}
);

UPDATE demo_tags_by_article
SET tags = tags + {'cassandra', 'wide-column'}
WHERE article_id = 55555555-5555-4555-8555-555555555555;
~~~

The resulting set contains `java`, `cassandra`, and `wide-column` (without repeating `cassandra`). Cassandra stores set elements sorted by the element type's comparator; **never rely on display order matching user insertion order**.

To remove a member:

~~~cql
UPDATE demo_tags_by_article
SET tags = tags - {'java'}
WHERE article_id = 55555555-5555-4555-8555-555555555555;
~~~

Removing elements creates deletion markers/tombstones per the collection storage model. A frequently mutated set with many deletions can accumulate tombstones; measure under realistic workloads.

### 4.2. How Far Does "Set Add Is Idempotent" Go?

**Adding the same value to a set** does not create two identical memberships, making it **safer to retry than list append**. However, never overgeneralize that to mean:

- Every set operation is an *exactly-once* transaction.
- A concurrent add and remove resolve according to user-perceived wall-clock time.
- Two clients replacing the entire set automatically merge their changes.
- Retries have no impact on write metadata, TTL, or other conflicts.

Cassandra resolves conflicts using write metadata. If adding/removing a tag requires strict business ordering, use events/versions or conditional writes (LWT). **Value-structure idempotency** does not equal **distributed workflow correctness**.

### 4.3. Uniqueness Does Not Normalize Data Automatically

In `set<text>`, `"Java"` and `"java"` are two distinct values. Likewise, two Unicode strings can look identical yet differ in NFC vs. NFD bytes.

If tags are case-insensitive, compute a **canonical tag** at the application boundary before binding—such as NFC plus a consistent case-folding policy. Never expect `set` to treat `"Café"` and `"café"` (with combining mark) as the same label.

### 4.4. Sets Do Not Create Reverse Indexes Automatically

`demo_tags_by_article` serves the query:

~~~cql
SELECT tags
FROM demo_tags_by_article
WHERE article_id = 55555555-5555-4555-8555-555555555555;
~~~

However, "fetch all articles tagged `cassandra`" is not served directly merely because `set<text>` exists. Some Cassandra versions/configurations offer indexing options on collection elements, yet **syntax and cost depend on version, cardinality, data distribution, and workload**.

When querying by tag is a primary read path at scale, evaluate an **inverted lookup table by tag + bucket**, as shown in the query-design section. Never scatter `ALLOW FILTERING` across the cluster to compensate for missing data models.

## 5. map<K,V>: Keyed Entries

### 5.1. Maps Are Not Arbitrary JSON Documents

`map<K,V>` stores **key → value** pairs. Keys within a map are unique; reassigning an existing key updates that entry's value under write rules rather than adding a duplicate key.

Example:

~~~cql
CREATE TABLE preferences_by_user (
    user_id uuid PRIMARY KEY,
    options map<text, text>
);

INSERT INTO preferences_by_user (user_id, options)
VALUES (
    66666666-6666-4666-8666-666666666666,
    {'theme': 'dark', 'font_size': '16', 'language': 'vi'}
);
~~~

A map makes sense here because the key set is controlled and reads usually fetch **the entire small configuration**. It does not provide arbitrary document-database querying or filtering.

This map should not become a dumping ground for:

- Every log message keyed by timestamp.
- Hundreds of thousands of ID → large object pairs.
- Data where each key has completely different lifecycle, TTL, permissions, or query patterns.
- Fields of different types all coerced into `text`, losing a clear type contract.

If the structure is fixed (`theme`, `font_size`, `language`) and requires per-field type enforcement, **separate columns or a UDT** may fit better. Maps shine when keys are dynamic yet **bounded**.

### 5.2. Setting One Entry, Merging Entries, and Deleting Keys

~~~cql
-- Set a single key in the map.
UPDATE preferences_by_user
SET options['theme'] = 'light'
WHERE user_id = 66666666-6666-4666-8666-666666666666;

-- Merge the specified entries into the map.
UPDATE preferences_by_user
SET options = options + {'font_size': '18', 'contrast': 'high'}
WHERE user_id = 66666666-6666-4666-8666-666666666666;

-- Delete a specific entry by key.
DELETE options['contrast']
FROM preferences_by_user
WHERE user_id = 66666666-6666-4666-8666-666666666666;
~~~

It is crucial to **distinguish setting a single entry** from **replacing the entire map**:

~~~cql
-- Replaces the ENTIRE collection with the new map,
-- not just updating one key inside the old map.
UPDATE preferences_by_user
SET options = {'theme': 'dark'}
WHERE user_id = 66666666-6666-4666-8666-666666666666;
~~~

After a full replacement, keys like `font_size` and `language` are gone from the new map. Rewriting the whole map also generates a collection-level tombstone and invites write races; avoid *read whole map → edit one key → write whole map* when multiple clients update concurrently.

### 5.3. Retrying Key Assignments and Concurrent Conflicts

With `options['theme'] = 'dark'`, resending the same key/value does not create duplicate keys. Yet that **does not guarantee**:

- Retrying an older mutation after a newer update arrived will have no effect under write-timestamp rules.
- Two writers modifying the same key follow client-side business order.
- Writing multiple keys across multiple rows/partitions becomes an ACID transaction.

For non-critical UI preferences, last-write-wins may be fine. For credit limits, access permissions, approval states, or concurrency-sensitive data, design explicit models and conditional writes rather than relying solely on a map.

### 5.4. Maps Have No Default "Priority Order"

Maps are stored/returned in key-comparator order, **not insertion order**. If business logic needs priority-ordered settings, store priority **explicitly** or model one row per item with a `priority` clustering key.

`map<text,text>` also does not validate that `theme` is in `dark/light` or that `font_size` is a valid integer. Enforce such constraints before binding, or choose a schema with strongly typed columns.

## 6. Non-Frozen vs. Frozen Collections: Essential Differences

In Cassandra, collections can be stored as **non-frozen** or **frozen**. This is a decision about **update semantics and comparison**, not just type syntax.

| Property | Non-frozen (typical) | `frozen<...>` |
|---|---|---|
| Logical representation | Individual elements/entries can be updated | Entire collection is **a single serialized value** |
| Updating one `set`/`map` element | Yes, via supported CQL operations | Cannot update individual elements; replace **the entire value** |
| Deleting individual entry/element | Yes, using matching syntax | Replace entire value; cannot DELETE one entry |
| Replacing collection | Can replace wholesale | Can replace wholesale |
| Tombstones | Can generate element/collection-level tombstones | Cell-level overwrite/delete; no per-element mutations |
| Best suited for | Small groups needing per-member edits | Small, immutable-by-business structures typically replaced as a whole |

Example:

~~~cql
CREATE TABLE visual_presets_by_id (
    preset_id uuid PRIMARY KEY,
    preset_name text,
    colors frozen<map<text, text>>
);

INSERT INTO visual_presets_by_id (preset_id, preset_name, colors)
VALUES (
    77777777-7777-4777-8777-777777777777,
    'Dark',
    {'background': '#111111', 'foreground': '#eeeeee'}
);
~~~

The `colors` column is a **frozen map**: you can `SET colors = { ... }` to replace it completely, but you **cannot** update `colors['background']` individually as with a non-frozen map.

~~~cql
UPDATE visual_presets_by_id
SET colors = {'background': '#000000', 'foreground': '#ffffff'}
WHERE preset_id = 77777777-7777-4777-8777-777777777777;
~~~

Some **frozen** collections are permitted in nested positions or keys where non-frozen collections are disallowed; however, **do not use large collections as primary keys** just to bypass regular collection restrictions. Keys should be stable, clearly scoped, and query-aligned; `uuid`, `text`, `timestamp`, or composite scalar keys are far easier to operate.

### 6.1. Nested Collections and UDTs

If you need a `list` of small objects, you can use **frozen UDTs** or nested collections as supported by your CQL version, but revisit the requirements before nesting deeply:

- **UDT** suits a structure with named fields and a stable schema.
- **Map** suits a group of homogeneously typed attributes with dynamic, bounded keys.
- **List/set** suit homogeneous elements with sequence/set semantics.
- **Separate table** suits cases where each element needs its own ID, TTL, updates, queries, or independent lifecycle.

Deeply nesting collections does not turn Cassandra into a document store: update semantics, tombstones, single-row size, and query capabilities remain firm boundaries.

## 7. Bounding Data in Collections: Keep Them Small and Bounded

This design rule matters more than syntactic choices between list and set.

**Collections work best when:**

1. Element count has a **business-enforced bound**.
2. Each element is **small** and typically returned with the rest of the row.
3. The application does not need to paginate element-by-element across thousands of items.
4. Unbounded growth or high concurrent contention per entry is not required.
5. Cluster-wide queries by individual element are not needed without a dedicated access path.

A few *illustrative* quantitative examples (not Cassandra's hard limits):

| Data | Business Rule | Choice |
|---|---|---|
| 5 pinned highlight IDs | Max 5, user-ordered | `list<uuid>` |
| 10 classification tags on an article | Max 10, unique | `set<text>` |
| 15 UI preferences | Max 15 dynamic keys, short values | `map<text,text>` |
| 50,000 clicks per day growing indefinitely | No small bound | **Multi-row table** |
| Millions of tenant configuration key/values | Independent lifecycle/query per key | **Table by tenant + key/bucket** |

CQL collections cannot be **arbitrarily paginated element-by-element** with the throughput of a clustered multi-row table. Reading large collections pulls excessive payload through coordinators and drivers, increasing network/GC pressure, cell/row size, and compaction/repair cost.

**Deletion impact:** removing an element from a non-frozen set/map or replacing/deleting a collection generates tombstones; frequently mutated lists also incur complex mutation overhead. Never build an oversized collection hoping compaction will turn it into an optimal table.

### 7.1. Empty, NULL, and UNSET Must Be Distinguished

In a **non-frozen collection**, an empty value may not exist as an independent "populated empty" cell; how CQL and drivers surface empty vs. null vs. unwritten values depends on the operation and version. With a **frozen** collection, the entire value is stored in a single cell, so empty representation follows cell-level rules.

Therefore, if the system must strictly distinguish:

- Tags have never been configured.
- Tags were configured and intentionally set to **0 tags**.
- All tags were deleted.

then **never rely on empty collection vs. NULL as the sole source of truth**. Store an explicit status/version field or model clear events. On PATCH, **UNSET** means leave the column untouched; **NULL** means delete in the mutation; empty values follow collection/cell semantics rather than guesswork.

### 7.2. NULL Is Not a Valid Element

Never insert **null elements** into a `list`/`set` or null keys/values into a `map` expecting JSON-like "missing field" semantics. Cassandra collections enforce strict element type rules; null elements or keys are not normal members.

If you need optional fields inside a composite structure, consider a UDT with nullable fields per CQL rules, or use a separate table/column with an explicit data model rather than arbitrary null sentinels inside collections.

## 8. Java Driver 4.x: Mapping Collections

Common mappings in Apache Cassandra Java Driver 4.x:

| CQL | Java Type | Write via `BoundStatementBuilder` | Read via `Row` |
|---|---|---|---|
| `list<uuid>` | `List<UUID>` | `setList(index, list, UUID.class)` | `getList("column", UUID.class)` |
| `set<text>` | `Set<String>` | `setSet(index, set, String.class)` | `getSet("column", String.class)` |
| `map<text,text>` | `Map<String,String>` | `setMap(index, map, String.class, String.class)` | `getMap("column", String.class, String.class)` |

Java generics erase element types at runtime, so these methods require the **element `Class`**—or `GenericType` for nested/complex types per driver APIs.

### 8.1. Writing All Three Collections with a Prepared Statement

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

// CqlSession session = ...; // Configured with cluster/keyspace.

UUID userId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID articleId = UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID highlightId = UUID.fromString("33333333-3333-4333-8333-333333333333");

Set<String> tags = Set.of("cassandra", "java");
List<UUID> pinned = List.of(highlightId);
Map<String, String> options = Map.of(
    "theme", "dark",
    "font_size", "16"
);

PreparedStatement insert = session.prepare(
    "INSERT INTO reading_state_by_user_article "
  + "(user_id, article_id, tags, pinned_highlight_ids, "
  + " display_options, updated_at) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, userId)
    .setUuid(1, articleId)
    .setSet(2, tags, String.class)
    .setList(3, pinned, UUID.class)
    .setMap(4, options, String.class, String.class)
    .setInstant(5, Instant.parse("2026-11-21T08:00:00Z"))
    .build();

session.execute(bound);
~~~

Use `Set.of`/`Map.of` (Java 9+) for small, immutable inputs; if older Java compatibility is needed, use `HashSet`/`HashMap` with appropriate validation. In asynchronous code, never mutate source collections or objects while codecs may still be serializing them; take immutable snapshots when needed.

### 8.2. Reading and Checking for NULL

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

PreparedStatement find = session.prepare(
    "SELECT tags, pinned_highlight_ids, display_options "
  + "FROM reading_state_by_user_article "
  + "WHERE user_id = ? AND article_id = ?");

Row row = session.execute(find.bind(userId, articleId)).one();

if (row == null) {
    // No row exists for this key.
} else {
    Set<String> storedTags = row.isNull("tags")
        ? null : row.getSet("tags", String.class);

    List<UUID> storedPinned = row.isNull("pinned_highlight_ids")
        ? null : row.getList("pinned_highlight_ids", UUID.class);

    Map<String, String> storedOptions = row.isNull("display_options")
        ? null : row.getMap("display_options", String.class, String.class);

    // Distinguish an absent row from an unset column.
}
~~~

If you need to modify a returned collection afterward, copy it into a new collection or DTO instead of assuming the driver-returned instance is mutable. For maps, check key presence and validity per contract: `get("theme") == null` does not prove by itself that the user explicitly deleted the theme.

### 8.3. Updating a Single Member from Java

To avoid reading an entire set and writing it all back, use CQL collection mutation operators:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.Set;

PreparedStatement addTag = session.prepare(
    "UPDATE reading_state_by_user_article "
  + "SET tags = tags + ? "
  + "WHERE user_id = ? AND article_id = ?");

session.execute(
    addTag.boundStatementBuilder()
        .setSet(0, Set.of("wide-column"), String.class)
        .setUuid(1, userId)
        .setUuid(2, articleId)
        .build()
);
~~~

Adding one member does not require the client to **read the existing set and rewrite the whole set**. Still, when concurrent writers add and remove the same element, outcomes follow Cassandra's concurrency/write-timestamp rules. Never assume an operation is business-safe in every case merely because there is no client-side read-modify-write.

For maps:

~~~java
PreparedStatement updateTheme = session.prepare(
    "UPDATE reading_state_by_user_article "
  + "SET display_options['theme'] = ? "
  + "WHERE user_id = ? AND article_id = ?");

session.execute(
    updateTheme.bind("light", userId, articleId)
);
~~~

When updating a single key, this is far cleaner than reading the entire map, mutating one key in Java, and writing the whole map back.

### 8.4. Handling Optional PATCH Fields

When a REST API sends a partial set of fields, distinguish:

- **Omitted**: preserve the existing column/collection by omitting it from the mutation or binding **UNSET** on a prepared statement.
- **Sent with a new value**: write the collection or apply the corresponding element mutation.
- **Sent with explicit null**: if the contract defines null as clear, explicitly delete (`NULL`/`DELETE`), understanding the tombstones generated.

Never call `setToNull` for omitted fields in a PATCH request. For non-frozen collections, treat a full replacement or deletion very differently from adding a single entry.

## 9. Concurrency: Why Replacing Entire Collections Loses Updates

Suppose initially:

~~~text
tags = {'java'}
~~~

Two clients read this state simultaneously:

~~~text
Client A: wants to add 'cassandra' -> computes {'java','cassandra'}
Client B: wants to add 'database'  -> computes {'java','database'}
~~~

If both execute `SET tags = {...}` to **replace the entire collection**, one write wins or overwrites the result so the tag added by the other client disappears. Client-side read–modify–write is **not serialized by Cassandra like an SQL transaction**.

Depending on the goal, choose:

1. **Element-level mutations** such as `tags = tags + {'cassandra'}`: avoids rewriting the entire collection just to add one tag, narrowing conflict scope.
2. **Conditional writes** with lightweight transactions (`IF`) or explicit versions when a workflow must verify state before updating; evaluate performance and CQL expressiveness.
3. **Immutable-ID event logs** followed by state aggregation when audit history or strict deduplication is needed.
4. **One row per member** when element counts are large and each member needs independent concurrency, TTL, or queries.

**Especially for lists**, appending inserts a new element and can duplicate on retries. If a user clicks "add highlight" and the client times out, use a stable `highlight_id` in a separate row if the requirement is "a given highlight exists at most once."

### 9.1. Do Not Equate Consistency Levels with Transactions

For example, `LOCAL_QUORUM` requires enough replicas to acknowledge per the replication strategy. It **does not** mean:

- Two clients replacing an entire map merge keys as intended.
- A list append executes *exactly once* across retries.
- Writes across two tables or partitions roll back like an ACID transaction.
- Reading a collection and updating it afterward is isolated from concurrent writers.

Each business requirement needs the right guarantee level: last-write-wins may be acceptable for UI preferences, whereas ledgers, credit limits, and permissions require stronger designs.

## 10. Designing Tables Instead of Unbounded Collections

### 10.1. Case Study: Highlights with Content and History

A user can create thousands of highlights for an article over time. Each highlight has its own ID, creation date, excerpt, and status; the app needs the 50 newest highlights on a given day.

**Do not** cram every highlight into an ever-growing `list<frozen<...>>` or `map<uuid,text>` in one row. Instead:

~~~cql
CREATE TABLE highlights_by_user_article_day (
    user_id uuid,
    article_id uuid,
    highlight_day date,
    highlighted_at timestamp,
    highlight_id uuid,
    excerpt text,
    PRIMARY KEY (
        (user_id, article_id, highlight_day),
        highlighted_at, highlight_id
    )
) WITH CLUSTERING ORDER BY (highlighted_at DESC, highlight_id ASC);
~~~

A matching query:

~~~cql
SELECT highlighted_at, highlight_id, excerpt
FROM highlights_by_user_article_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND article_id = 22222222-2222-4222-8222-222222222222
  AND highlight_day = '2026-11-21'
LIMIT 50;
~~~

Benefits:

- Each highlight has its **own primary key**, making retries straightforward.
- You can read the **top 50 rows** via clustering order without fetching a huge collection.
- You can update or delete individual highlights with row-level tombstone visibility.
- You can tune daily or hourly buckets as data scales.

Ensure `highlight_day` is computed from `highlighted_at` using an **agreed time zone**; computing UTC on write and local time on read causes clients to query the wrong partition. When daily volume is huge, measure partition size and consider sharding or smaller buckets.

### 10.2. Case Study: Finding Articles by Tag

If the primary query is "find articles tagged `cassandra` on a given day for a tenant," a clear access path is:

~~~cql
CREATE TABLE article_refs_by_tenant_tag_day (
    tenant_id uuid,
    tag text,
    tag_day date,
    tagged_at timestamp,
    article_id uuid,
    PRIMARY KEY ((tenant_id, tag, tag_day), tagged_at, article_id)
) WITH CLUSTERING ORDER BY (tagged_at DESC, article_id ASC);
~~~

Query:

~~~cql
SELECT tagged_at, article_id
FROM article_refs_by_tenant_tag_day
WHERE tenant_id = 88888888-8888-4888-8888-888888888888
  AND tag = 'cassandra'
  AND tag_day = '2026-11-21'
LIMIT 50;
~~~

This is an **inverted lookup table** serving tag queries, not an automatic mirror of `set<text>`. When tags are added or removed, the system must update this mapping and handle retries, reconciliation, and deletions/TTL per policy.

If millions of articles share the same tag in one day, the `(tenant_id, tag, tag_day)` partition can still become large or hot; design buckets/shards and pagination around actual workload. A query-driven table is not free; measure real throughput and partition sizes.

### 10.3. Separate Table vs. Index?

There is no single universal answer. Cassandra offers secondary indexes and Storage-Attached Indexes (SAI) depending on version and deployment, some supporting queries on collections. However, verify **Cassandra version**, indexed collection kind, supported operators, cardinality, selectivity, partition size, and read/write overhead.

For critical query paths, start with a table having an **aligned partition key**. Choose an index only after load testing under realistic traffic with clear operational plans for replication, compaction, and repair impact.

## 11. Collections and Tombstones, TTL, Compaction, and Repair

### 11.1. Element- and Collection-Level Tombstones

Cassandra uses tombstones to record deletions across replicas. For collections:

- Removing an element from a `set` or a key from a `map` creates deletion markers so older data cannot resurrect.
- Replacing an entire **non-frozen collection** can write a collection-level tombstone to shadow prior elements absent from the new value.
- For `list`, positional/value additions and removals plus internal ordering can incur more complex costs and tombstones than "a simple Java array."
- With **frozen**, the collection is handled as a single value rather than independent element mutations.

Tombstones are normal when business operations genuinely delete data. Yet continuously deleting and rewriting a 10,000-key map just to change `theme` creates unnecessary load compared to updating a single entry.

### 11.2. TTL and Data Lifecycle

TTL in Cassandra is specified in **seconds** for written data, and expiration produces tombstones. In a non-frozen collection, individual mutations/elements can carry storage lifetimes affected by their respective writes. Never assume all elements share the same expiration time if added at different times.

If elements need **independent lifecycles/TTLs**, verify whether CQL updates apply TTL as intended; often one row per element is far clearer. For requirements demanding "exact expiration time per item," an explicit `expires_at timestamp` and deadline-driven query model is usually safer than treating TTL as a scheduler.

### 11.3. Replication and Repair Do Not Fix Logic Bugs

- **Replication** stores mutations/values across replicas by partition key.
- **Repair** converges replica state; it does not restore elements lost when an application accidentally overwrote an entire collection.
- **Compaction** merges SSTables and clears eligible tombstones; it does not turn a giant collection into a well-partitioned table.
- **Consistency levels** govern replica acknowledgments; they cannot eliminate duplicate list appends or lost updates from read–modify–write races.

If the system syncs collections across regions or offline clients, define explicit merge, conflict, and versioning strategies. A Cassandra collection is not a full CRDT list/map/set built for arbitrary offline sync.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `list` for every click/log event | Unbounded collection, hard to paginate or edit items | One row per event, clustered by time |
| Retrying `list = list + [x]` after timeout | `x` can appear twice | Stable event IDs, separate event table if needed |
| Using `set` when insertion order is needed | No business insertion order | Small `list` or table with clustering order |
| Using `list` when uniqueness is required | Duplicate values can be added | `set` or stable ID/key in a table |
| Assuming `map` keeps priority order | No insertion order | Store priority/order explicitly |
| Rewriting an entire map to update one key | Unintended overwrites and tombstones | `map['key'] = value` on non-frozen maps |
| Replacing an entire set from two racing clients | Newly added members can be lost | Element mutations or versions/conditional writes |
| Using a non-frozen collection as primary key | Invalid per type constraints | Scalar keys; keep collections as data columns |
| Updating a single entry of `frozen<map<...>>` | Per-entry mutation not supported | Replace entire frozen value or use non-frozen |
| Treating tags with different Unicode normalization as equal | Set holds both variants | Canonicalize before binding |
| Storing `null` as an element/key | Not a valid regular member | Dedicated status/column/UDT design |
| Treating an empty collection as a strict business state | Empty vs. null can be ambiguous | Store an explicit flag/status column if needed |
| Cluster-wide `tags CONTAINS ...` queries without index design | Unsuitable / high cost | Tag-keyed query table or benchmarked index |
| Letting a collection grow huge in one row | High network, GC, I/O, compaction/repair cost | Bound size; split into multiple rows |
| Treating `LOCAL_QUORUM` as exactly-once | Retry/concurrency bugs still occur | Idempotency, stable keys, versioning/LWT as needed |

## 13. Practice Exercises

### Exercise 1 — Choosing the Right Type

An e-reader system has:

1. Up to 4 highlight IDs pinned by the user in order.
2. Up to 8 unique category tags.
3. 12 key-based UI preferences.
4. Millions of page-scroll events queried over time.

**Suggested answer:** (1) `list<uuid>` with concurrency/retry controls; (2) `set<text>`; (3) `map<text,text>` or typed columns/UDT if the schema is fixed; (4) **a multi-row event table** with partition buckets and time clustering.

### Exercise 2 — Retrying a List

A client sends `UPDATE ... SET pinned_ids = pinned_ids + [id]`, gets a timeout, and retries.

**Question:** can the client rely on `list` to guarantee `id` appears only once?

**Answer:** no. The append may be applied multiple times. If each highlight ID must appear at most once, use a row keyed by a stable `highlight_id` or dedicated idempotency handling; `set<uuid>` fits only when ordering is not needed.

### Exercise 3 — Sets and Unicode

A `set<text>` receives `"Java"`, `"java"`, `"café"` (NFC), and `"café"` (NFD).

**Question:** does Cassandra automatically treat those visually similar pairs as one member?

**Answer:** no. Sets deduplicate by exact CQL value bytes, not automatic case folding or Unicode normalization. The application must enforce one consistent canonicalization policy.

### Exercise 4 — Map Update or Replace?

Initially:

~~~text
options = {'theme': 'dark', 'font_size': '16'}
~~~

Executed:

~~~cql
UPDATE preferences_by_user
SET options = {'theme': 'light'}
WHERE user_id = 66666666-6666-4666-8666-666666666666;
~~~

**Question:** is `font_size` guaranteed to be preserved?

**Answer:** no. Assigning the **entire map** replaces the collection with a map containing only `theme`. To change only the theme, use `SET options['theme'] = 'light'`.

### Exercise 5 — Designing Tag Queries

Schema `articles_by_id(article_id uuid PRIMARY KEY, tags set<text>)`; requirement: "50 newest articles tagged `cassandra` by tenant/day."

**Question:** does simply changing `set<text>` to `list<text>` solve this?

**Answer:** no. You need an access path keyed by `tenant + tag + day` clustered by timestamp, or a proven, sufficiently performant index; the collection type alone does not enable that query.

## 14. Checklist for Reviewing Cassandra Collections

- [ ] Does the data require **ordering**, **uniqueness**, or **key → value** lookup?
- [ ] Are there concrete bounds on **element count**, element size, and total collection size?
- [ ] Do you need to query, paginate, or update thousands of items independently? If so, consider a **multi-row table**?
- [ ] If choosing **list**, is idempotency under retries required, and have duplicate append/prepend risks been handled?
- [ ] If choosing **set**, are you mistakenly expecting insertion order or automatic case folding/Unicode normalization?
- [ ] Does **map** genuinely require dynamic keys, or would typed columns/a UDT give a clearer schema?
- [ ] Is **frozen = replace entire value** understood vs. non-frozen per-element mutations per supported syntax?
- [ ] Are read–modify–write full-map/set replacements avoided when multiple clients can write concurrently?
- [ ] Are **NULL, UNSET, and empty** clearly distinguished per the domain contract?
- [ ] Do all operations supply the **full partition key**; is a lookup table or index needed to search by element?
- [ ] Does the Java Driver use `setList/getList`, `setSet/getSet`, and `setMap/getMap` with matching generic element classes?
- [ ] Have TTL, tombstones, compaction, repair, and consistency been sized/designed around per-element lifecycles?
- [ ] Do retries keep business IDs/keys stable without relying on consistency levels for exactly-once guarantees?
- [ ] Are partition growth limits and a migration plan ready if the collection outgrows initial projections?

## References

- [Apache Cassandra — CQL Data Types, Collections](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra Java Driver 4.x — Object Mapping / CQL to Java](https://apache.github.io/cassandra-java-driver/4.18.0/core/data_types/).

**Remember:** use **`list`** for a **small, ordered** sequence, **`set`** for a **small, duplicate-free** set, and **`map`** for **small, bounded key/value** pairs. Non-frozen collections allow supported element-level mutations; frozen collections behave as a single value replaced as a whole. Whenever you need many elements, long histories, pagination, or lookups by member, use **Cassandra rows with query-driven primary keys and clustering columns**, while handling retries, concurrency, tombstones, and repair according to distributed semantics.
