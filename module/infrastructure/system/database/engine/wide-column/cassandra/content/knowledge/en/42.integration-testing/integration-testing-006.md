# Testing NULL/UNSET, Collections, UDTs, and Boundary Data Types

> **Chapter:** Integration Testing  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — understanding distributed architecture, Apache Cassandra's wide-column model, partition keys, query-driven table design, consistency, CQL, replication, compaction, repair, error handling, and Java connectivity.

A Java API receives a profile update payload:

~~~json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "note": null,
  "tags": [],
  "address": { "city": "Hanoi" }
}
~~~

At first glance, a team might assume `note = null` means “leave unchanged”, `tags = []` means “clear all”, and `address.city` changes while keeping other fields intact. **Cassandra does not infer that intent automatically.** With CQL prepared statements:

- **`UNSET`** means *do not write to the bound column*.
- **`NULL`** on a regular column means *delete the value*, creating a **tombstone**.
- Empty collections and missing collections may be **indistinguishable after a round-trip**; list/set/map have distinct codec, mutation, and ordering rules.
- `frozen<UDT>` is written as **a single value**, whereas non-frozen UDTs support **per-field** updates.
- `timestamp`, `date`, `decimal`, `varint`, `blob`, and Unicode types have boundary values that easily expose type-conversion bugs.

Mocking `CqlSession` in unit tests **cannot verify** these semantics completely. This lesson builds an **automated integration test suite running against real Cassandra via Testcontainers/JUnit**, while specifying which cases must also be tested on a multi-node topology.

**Version scope:** main examples use Apache Cassandra **4.1.x** in a container, **Apache Java Driver 4.19 API**, Java **17**, JUnit Jupiter 5, and Testcontainers **2.0.x**. You can extend the compatibility matrix with Cassandra 5.0; specific test semantics must be verified against the locked server/driver versions. Testcontainers **1.x** places `CassandraContainer` in a different package than **2.x**. Do not swap dependency versions arbitrarily when copying code.

## 1. Learning Outcomes and Testing Philosophy

After completing this lesson, you will be able to:

1. Clearly describe `ABSENT`, `UNSET`, `NULL`, `EMPTY`, and `NON_EMPTY` in **CQL context**, without treating them as five distinguishable states on every column.
2. Use `PreparedStatement.bind()`, `BoundStatement.unset()`, `setToNull()`, and `isSet()` to test write effects on an existing row.
3. Prove that `UNSET` **preserves** old values, while `NULL` on regular columns **deletes** them and can create tombstones.
4. Test that PKs cannot be NULL/UNSET, while distinguishing a non-existent row from a null column in a live row.
5. Round-trip `list/set/map`, avoid relying on set/map iteration order, and test null elements and empty collections accurately.
6. Build and read `UdtValue`, testing `frozen<UDT>` vs non-frozen UDTs, missing/null fields, schema type evolution, and codecs.
7. Test boundaries of `tinyint/smallint/int/bigint/varint/decimal`, pre-1970 timestamps, leap days, precision, and Unicode.
8. Set up automated tests against real Cassandra with isolation, setup/teardown, dependency pinning, and CI independent of personal databases.
9. Separate **correctness/codec** tests on one node from **RF/CL, repair, failure/retry** tests requiring multiple nodes.
10. Write assertions sensitive to schema, timeouts, TTLs, and data modeling rather than brittle `cqlsh` output or log text matching.

### 1.1. A Cassandra-Appropriate Test Pyramid

| Layer | What It Verifies | What It Cannot Prove |
|---|---|---|
| Unit: codecs/utilities/DTOs | Unicode normalization, JSON parsing, validation, local mapping | Whether the CQL server accepts the mutation |
| Integration: **1 real Cassandra** | NULL/UNSET, CQL types, codecs, UDTs, collections, PK rules, basic LWT | Multi-node quorum, split-brain, repair, DC failover |
| Integration: **multi-node** | RF/CL, replica failures, read/write timeouts, topology changes | Full production load and long-term tombstone cost |
| End-to-end: HTTP → service → Cassandra | Absent/null/empty contracts, idempotency, serialization, auth | Cannot replace dedicated schema/driver tests |
| Load/soak/chaos | Hot partitions, p99, TTL/tombstone/compaction, long-term recovery | Cannot replace exact value assertions |

**Golden rule:** If an issue occurs at the wire protocol, CQL parser, server storage engine, or codec level, there must be **at least one test hitting real Cassandra**, not merely a mocked repository.

## 2. Defining NULL, UNSET, and Existence States

### 2.1. Similar Words at Different Layers

| Concept | Where It Appears | Effect |
|---|---|---|
| **ABSENT JSON field** | HTTP request omits the `note` key | Application **must decide** between UNSET, default, or validation error |
| **JSON `null`** | Request contains `"note": null` | Application **must define** whether to delete or ignore; never auto-equate with UNSET |
| **UNSET bind variable** | Java Driver native protocol v4+ | CQL skips assignment for that bound column, creating no tombstone for it |
| **NULL bind value** | `BoundStatement.setToNull` or binding Java `null` | On writable regular columns, deletes the value and creates a mutation tombstone |
| **CQL empty string** | `''` / Java `""` | A **zero-length string**, distinct from NULL in text columns |
| **Empty collection** | `[]`, `{}`, Java `List.of()`/`Set.of()` | Not equivalent to “do not touch column”; limited distinction from NULL |
| **Row absent** | `SELECT ... WHERE PK=?` returns no row | Distinct from a live row whose `note` is null |

Separate **API state** from **CQL state**. If your system accepts PATCH requests, use a DTO that represents all three states—**field absent / explicit null / value**—such as a JSON presence wrapper, instead of relying on a single nullable Java property to guess whether the user meant delete or keep.

### 2.2. Prepared UPDATE Semantics

Suppose the row already has `note='keep-me'` and `score=7`:

~~~text
UPDATE ... SET note=?, score=? WHERE profile_id=?

bind(note=UNSET, score=8)     -> note remains 'keep-me'; score becomes 8
bind(note=NULL,  score=UNSET) -> note has no value; score remains 8
bind(note='',    score=UNSET) -> note becomes empty string; score remains 8
~~~

While the row still holds live data in another column, `SELECT note,score` reads `note=null` and `score=8`. However, CQL queries are **not an API asking “was this column never written or deleted?”**: both can return null, requiring sequenced tests and understanding of tombstones/metadata.

### 2.3. Java Driver 4.x: UNSET Supported in Protocol v4+

Calling `PreparedStatement.bind()` **with no arguments** leaves bind variables in the **UNSET** state where protocol supports it; `unset(i)` resets a previously set variable back to UNSET.

~~~java
PreparedStatement ps = session.prepare(
    "UPDATE it_lab.profile_by_id " +
    "SET note = ?, score = ? WHERE profile_id = ?");

BoundStatement base = ps.bind();
assert !base.isSet(0);                  // note: UNSET
assert !base.isSet(1);                  // score: UNSET

BoundStatement withKey = base.setUuid(2, id);
BoundStatement clearNote = withKey.setToNull(0);
BoundStatement keepNote = clearNote.unset(0);

assert clearNote.isSet(0);              // explicit NULL was set
assert !keepNote.isSet(0);              // reverted to UNSET
~~~

**Driver 4.x statements are immutable:** `setUuid()`, `setToNull()`, and `unset()` all return a **new object**. Never write `base.unset(0); session.execute(base);` thinking the original variable changed. Crucially, **never pass UNSET for a primary key or use it as a WHERE predicate**; Cassandra rejects invalid positions.

### 2.4. NULL Can Create Tombstones

In Cassandra, deleting a column is represented by a **tombstone** so peer replicas do not resurrect the old value during data reconciliation. Test:

~~~sql
UPDATE it_lab.profile_by_id
SET note = null
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
~~~

To verify **semantics**, assert `row.isNull("note")` and verify other columns remain unchanged. **Do not** require tests to inspect SSTable files directly to prove CQL NULL—that depends on flushes, compaction, and implementation details. For workloads frequently writing nulls, tombstones can impact reads/compaction; measure at the cluster level rather than extrapolating exact tombstone counts from one unit test.

### 2.5. When to Distinguish ABSENT, NULL, and EMPTY via Explicit Schema

If business logic must distinguish **“user never sent tags”** from **“user cleared all tags”**, do not rely on `getSet("tags") == null` because Cassandra/codecs may normalize both to an empty collection. Design explicitly:

- A `tags_state`/`tags_specified` column or intentional version/operation marker.
- A JSON API contract defining absent = preserve, null = delete, empty = empty set.
- Updates to related state columns must stay consistent with partition and mutation semantics.
- For workflows needing compare-and-set, consider LWT/versioning rather than relying on default timestamps to decide winners.

## 3. Setting Up a Real Test Environment with Testcontainers

### 3.1. Versions and Infrastructure Requirements

Hands-on examples use **Testcontainers 2.0.x** and **Java 17**; code imports `CassandraContainer` from **`org.testcontainers.cassandra`**. Older Testcontainers 1.x uses `org.testcontainers.containers.CassandraContainer` and artifact `org.testcontainers:cassandra`; **do not mix the two generations**. A working container runtime/Docker engine is required; Testcontainers manages start/stop instead of requiring everyone to share one local Cassandra install.

Illustrative Gradle Groovy DSL:

~~~groovy
dependencies {
    testImplementation "org.junit.jupiter:junit-jupiter:5.11.4"
    testImplementation "org.testcontainers:testcontainers-cassandra:2.0.5"
    testImplementation "org.testcontainers:testcontainers-junit-jupiter:2.0.5"

    // Java Driver version matching the application's BOM/stack:
    implementation "org.apache.cassandra:java-driver-core:4.19.0"
}

test {
    useJUnitPlatform()
}
~~~

**These versions are pinned examples**, not a mandate to use these exact patches across every project. If a Spring Boot project manages JUnit/driver via a BOM, prefer the tested BOM; never force two conflicting Java Driver implementations onto the classpath. The lesson uses `cassandra:4.1` for convenience; **in CI, pin an approved patch/digest** for reproducibility and image change control.

### 3.2. JUnit 5 Container and Session Lifecycle

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.TestInstance;
import org.testcontainers.cassandra.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CassandraTypesIT {
    @Container
    static final CassandraContainer CASSANDRA =
        new CassandraContainer(DockerImageName.parse("cassandra:4.1"));

    private CqlSession session;

    @BeforeAll
    void init() {
        session = CqlSession.builder()
            .addContactPoint(CASSANDRA.getContactPoint())
            .withLocalDatacenter(CASSANDRA.getLocalDatacenter())
            .build();
        // Create schema in order: keyspace -> UDT -> table.
        // Full CQL is in Section 4; call session.execute per statement.
    }

    @AfterAll
    void close() {
        if (session != null) session.close();
    }
}
~~~

By default, Testcontainers Cassandra is a **single node**; never use this test to claim `QUORUM/LOCAL_QUORUM` works when a replica is Down. The JUnit extension typically manages static containers per **class lifecycle**. Never enable parallel execution over **shared schemas/rows** without an isolation strategy; Testcontainers' JUnit extension docs cover only tested configurations.

### 3.3. Spring Boot Integration Tests: Pick the Right Entrypoint

When testing entity converters, repositories, or Spring Data:

~~~java
// Pattern only, not a standalone file:
//
// @SpringBootTest
// @Testcontainers
// class ProfileRepositoryIT {
//   @Container static final CassandraContainer CASSANDRA = ...;
//
//   @DynamicPropertySource
//   static void cassandraProps(DynamicPropertyRegistry registry) {
//       registry.add("spring.cassandra.contact-points",
//           () -> CASSANDRA.getHost() + ":" + CASSANDRA.getMappedPort(9042));
//       registry.add("spring.cassandra.local-datacenter",
//           CASSANDRA::getLocalDatacenter);
//       registry.add("spring.cassandra.keyspace-name", () -> "it_lab");
//   }
// }
~~~

`@DynamicPropertySource` is one way to inject dynamic endpoints in Spring Boot 3.x; with compatible Spring Boot Testcontainers integration, `@ServiceConnection` can supply connection details. **Do not blindly enable both** when they supply conflicting configs. The Spring context must be created **after endpoints are known**; the schema/keyspace must exist before repositories initialize against it.

### 3.4. Avoiding Flakiness from Cassandra Startup and Schema Agreement

Testcontainers has a wait strategy, yet **container ready does not mean every schema mutation has been received and agreed** on a multi-node topology. Rules:

1. Wait for the native protocol port and a working session connection.
2. Create keyspace, then types, then tables via CQL while checking outcomes.
3. On multi-node clusters, await **schema agreement** and stable topology before preparing statements.
4. Run tests with per-case unique IDs; never reuse a hardcoded UUID across parallel tests.
5. If a container fails to start, collect container, native transport/GC, and driver startup logs; **never** bump fixed sleeps indefinitely.

## 4. Test Schema Covering All Data Types

### 4.1. Keyspace: RF=1 for Single-Node Integration Tests

~~~sql
CREATE KEYSPACE IF NOT EXISTS it_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 1
}
AND durable_writes = true;
~~~

`datacenter1` is the typical default DC name in Testcontainers Cassandra images; **verify `CASSANDRA.getLocalDatacenter()` at runtime**. If different, update the CQL accordingly. **RF=1 is not a production config**; it allows testing codec/CQL semantics without requiring three nodes.

### 4.2. Create the UDT Before the Table

~~~sql
CREATE TYPE IF NOT EXISTS it_lab.address_info (
  street text,
  city text,
  postal_code text
);

CREATE TABLE IF NOT EXISTS it_lab.profile_by_id (
  profile_id uuid PRIMARY KEY,
  note text,
  score int,
  active boolean,
  priority_tiny tinyint,
  short_value smallint,
  long_value bigint,
  huge_value varint,
  amount decimal,
  created_at timestamp,
  event_day date,
  event_time time,
  tags set<text>,
  aliases list<text>,
  quotas map<text, int>,
  home frozen<it_lab.address_info>,
  office it_lab.address_info,
  blob_value blob,
  source_ip inet
);
~~~

Columns chosen for testing:

- **`note/score/active`:** NULL vs UNSET and primitive defaults (0/false).
- **`priority_tiny/short_value/long_value/huge_value/amount`:** boundary values, overflow, and precision.
- **`created_at/event_day/event_time`:** time precision/UTC/calendar dates.
- **`tags/aliases/quotas`:** set/list/map, empty states, duplicates, element typing.
- **`home`:** frozen UDT, updated as a **whole value**.
- **`office`:** non-frozen UDT, updatable per field.
- **`blob_value/source_ip`:** binary buffers and network addresses.

If your server/version lacks support for a type or syntax, **do not ignore errors in tests**: document the version feature matrix and consult that release's CQL docs. On a fresh Testcontainers 4.1 instance, the schema must be created explicitly—never assume it already exists just because `IF NOT EXISTS` is used.

### 4.3. Setup Sequence Sample in Java

~~~java
// Inside @BeforeAll after CqlSession has been created:
session.execute("CREATE KEYSPACE IF NOT EXISTS it_lab " +
    "WITH replication = {'class': 'NetworkTopologyStrategy', " +
    "'" + CASSANDRA.getLocalDatacenter() + "': 1}");

session.execute("CREATE TYPE IF NOT EXISTS it_lab.address_info (" +
    "street text, city text, postal_code text)");

session.execute("CREATE TABLE IF NOT EXISTS it_lab.profile_by_id (" +
    "profile_id uuid PRIMARY KEY, note text, score int, active boolean, " +
    "priority_tiny tinyint, short_value smallint, long_value bigint, " +
    "huge_value varint, amount decimal, created_at timestamp, " +
    "event_day date, event_time time, tags set<text>, aliases list<text>, " +
    "quotas map<text,int>, home frozen<it_lab.address_info>, " +
    "office it_lab.address_info, blob_value blob, source_ip inet)");
~~~

In real projects, **use controlled SQL/CQL migration files or schema fixtures** instead of duplicating DDL across test classes. The Java snippet above is self-contained for lesson clarity without external repository files; it does not test TLS, password auth, or rolling migrations.

## 5. First Test: NULL Differs from UNSET on the Same Row

### 5.1. Preparing Data Before Each Case

Each test generates its own UUID so tests never collide:

~~~java
UUID id = UUID.randomUUID();

PreparedStatement seed = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, note, score) VALUES (?, ?, ?)");
session.execute(seed.bind(id, "preserve-me", 7));
~~~

**Never** run `TRUNCATE TABLE` before every test if multiple tests share one container; `TRUNCATE` introduces barriers/overhead and can wipe data belonging to parallel tests. When tests finish, container teardown cleans up; if explicit cleanup is needed, `DELETE` by the test's UUID while noting it creates tombstones.

### 5.2. UNSET `note` in UPDATE Preserves the Previous Value

~~~java
PreparedStatement update = session.prepare(
    "UPDATE it_lab.profile_by_id SET note = ?, score = ? " +
    "WHERE profile_id = ?");

BoundStatement withUnset = update.bind()
    .setInt(1, 8)     // new score
    .setUuid(2, id);  // note (index 0) left UNSET

org.junit.jupiter.api.Assertions.assertFalse(withUnset.isSet(0));
session.execute(withUnset);

Row afterUnset = session.execute(
    session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id WHERE profile_id = ?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(afterUnset);
org.junit.jupiter.api.Assertions.assertEquals(
    "preserve-me", afterUnset.getString("note"));
org.junit.jupiter.api.Assertions.assertEquals(
    8, afterUnset.getInt("score"));
~~~

Because `note` is UNSET, no mutation touches that column; `score` updates to 8. Avoid testing an UPDATE that is **entirely UNSET**, as server no-op handling may trigger behavior unrelated to this topic.

### 5.3. NULL `note` Deletes the Value Without Deleting `score`

~~~java
BoundStatement withNull = update.bind()
    .setToNull(0)      // note = NULL (delete column)
    .setUuid(2, id);   // score (index 1) remains UNSET

org.junit.jupiter.api.Assertions.assertTrue(withNull.isSet(0));
org.junit.jupiter.api.Assertions.assertFalse(withNull.isSet(1));
session.execute(withNull);

Row afterNull = session.execute(
    session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id WHERE profile_id = ?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(afterNull);
org.junit.jupiter.api.Assertions.assertTrue(afterNull.isNull("note"));
org.junit.jupiter.api.Assertions.assertEquals(
    8, afterNull.getInt("score"));
~~~

Here the row survives because `score` still holds a value; when only a PK exists and every cell is deleted, row markers/results have distinct semantics. **Never assert a row disappears merely because one non-key column was set to NULL.**

### 5.4. Empty String Is Not NULL

~~~java
BoundStatement empty = update.bind()
    .setString(0, "")
    .setUuid(2, id);
session.execute(empty);

Row r = session.execute(
    session.prepare("SELECT note FROM it_lab.profile_by_id " +
                    "WHERE profile_id=?").bind(id)).one();
org.junit.jupiter.api.Assertions.assertNotNull(r);
org.junit.jupiter.api.Assertions.assertFalse(r.isNull("note"));
org.junit.jupiter.api.Assertions.assertEquals("", r.getString("note"));
~~~

This is a critical regression test for REST/API clients sending `""`, `null`, or omitting the field. If the application normalizes empty strings to null before binding, integration tests must reflect **that exact contract**.

## 6. Invalid NULL/UNSET Cases

### 6.1. Primary Key Must Have a Value

A Cassandra row is identified by its **full primary key**. You cannot insert/update a row with a `null`/UNSET partition key; a WHERE clause on a key cannot use an unbound value.

~~~java
PreparedStatement insert = session.prepare(
    "INSERT INTO it_lab.profile_by_id (profile_id, note) " +
    "VALUES (?, ?)");

// profile_id is not bound, meaning UNSET.
BoundStatement missingPk = insert.bind()
    .setString(1, "bad-key");

// profile_id is explicitly bound to NULL.
BoundStatement nullPk = insert.bind()
    .setToNull(0)
    .setString(1, "bad-key");

// On compatible drivers/servers, these requests must be rejected.
// Check the release-appropriate error/cause; do not match exact text.
org.junit.jupiter.api.Assertions.assertThrows(
    com.datastax.oss.driver.api.core.servererrors.InvalidQueryException.class,
    () -> session.execute(missingPk));
org.junit.jupiter.api.Assertions.assertThrows(
    com.datastax.oss.driver.api.core.servererrors.InvalidQueryException.class,
    () -> session.execute(nullPk));
~~~

If a driver/framework **blocks the request before sending it to the server**, the exception class may differ; assert the principle “mutations with missing PKs cannot succeed” and classify by the rejecting layer rather than forcing a brittle class match. Also test **clustering keys** on composite-key tables; they cannot be NULL/UNSET when CQL requires the full key for a mutation.

### 6.2. UNSET Is Not a Wildcard in WHERE

Wrong:

~~~sql
-- WHERE profile_id = ? with UNSET bound does NOT select all profiles.
SELECT note FROM it_lab.profile_by_id WHERE profile_id = ?;
~~~

Similarly, `UNSET` is not an “IS NULL” operator across rows. Cassandra is not a relational SQL engine performing arbitrary NULL scans. If the app needs “all profiles without a note”, **design a query-driven table/index** or offline pipeline rather than leaving `profile_id` unbound hoping the server filters for you.

### 6.3. Non-Existent Row Differs from a Null Column

~~~java
UUID unknown = UUID.randomUUID();
Row missing = session.execute(
    session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(unknown)).one();

org.junit.jupiter.api.Assertions.assertNull(missing);
~~~

For a live row whose `note` was deleted, you get `Row != null` and `row.isNull("note") == true`. Never write:

~~~java
// WRONG: row may be null because the key does not exist.
// String note = result.one().getString("note");
~~~

When reading primitives (`int/boolean`), the driver returns default `0/false` for CQL NULL; call `Row.isNull("score")` first whenever business logic distinguishes **absent value** from **zero**.

### 6.4. Null in Column Names and CQL Identifiers

Bind markers `?` represent **values**, never identifiers (table, column, or keyspace names). A request carrying a null or arbitrary field name in JSON must never be concatenated directly into a CQL string. If an app supports patching multiple fields, use a **property allowlist and static CQL fragments**, binding values via prepared statements.

## 7. Collections: list, set, map, and Round-Trip Tests

### 7.1. Three Collections with Distinct Semantics

| Type | Java Driver Getter | Semantics to Test |
|---|---|---|
| `list<text>` | `row.getList("aliases", String.class)` | Ordered; duplicates **preserved** |
| `set<text>` | `row.getSet("tags", String.class)` | No duplicates; never rely on iteration order |
| `map<text,int>` | `row.getMap("quotas", String.class, Integer.class)` | Unique keys; compare key-value pairs, not iteration order |

Collections suit **small, bounded sets**. They are poor choices for storing millions of access events: collections are typically read as one large unit, do not support inner paging, have size limits, and introduce dedicated tombstone/latency risks.

### 7.2. Writing Three Collections and Reading Typed Values

~~~java
UUID id = UUID.randomUUID();

PreparedStatement ps = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, tags, aliases, quotas) " +
    "VALUES (?, ?, ?, ?)");

Set<String> tags = Set.of("new", "priority");
List<String> aliases = List.of("Lan", "Lan", "LAN");
Map<String, Integer> quotas = Map.of("daily", 0, "monthly", 100);

BoundStatement bs = ps.bind()
    .setUuid(0, id)
    .setSet(1, tags, String.class)
    .setList(2, aliases, String.class)
    .setMap(3, quotas, String.class, Integer.class);
session.execute(bs);

Row r = session.execute(
    session.prepare(
        "SELECT tags, aliases, quotas FROM it_lab.profile_by_id " +
        "WHERE profile_id=?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(r);
org.junit.jupiter.api.Assertions.assertEquals(
    tags, r.getSet("tags", String.class));
org.junit.jupiter.api.Assertions.assertEquals(
    aliases, r.getList("aliases", String.class));
org.junit.jupiter.api.Assertions.assertEquals(
    quotas, r.getMap("quotas", String.class, Integer.class));
~~~

**Why assert with `equals`:** Sets and Maps do not promise iteration order matching input; JUnit's order-sensitive `assertIterableEquals` is unsuitable. Lists are **ordered** and permit duplicates, so assert the exact list.

### 7.3. Null or Empty Collections May Read Back Identically

Cassandra and Java Driver **do not guarantee a distinct “empty collection” state separate from “unset/missing collection” across all versions/codecs**. Built-in driver codecs commonly decode an absent/null collection as an **empty Java collection**; therefore:

~~~java
// Verify contract per driver/version.
List<String> aliases = row.getList("aliases", String.class);
Set<String> tags = row.getSet("tags", String.class);

// With built-in codecs, both may be empty whether the CQL column
// is empty or absent. DO NOT blindly assert null.
org.junit.jupiter.api.Assertions.assertTrue(aliases.isEmpty());
org.junit.jupiter.api.Assertions.assertTrue(tags.isEmpty());
~~~

**Important:** this holds only when the test wrote the column expecting it to be **empty** (e.g., a new row with an empty collection); never apply this to an arbitrary dataset. `row.isNull("tags")` may reflect wire-level distinctions depending on representation and frozen/multi-cell storage, yet **does not establish a stable business-level distinction** between “never sent” and “sent empty”.

To test HTTP PATCH intent differentiation:

1. Seed an initial tag set (e.g., `{"a","b"}`).
2. Send a request with **field absent** → service binds UNSET → tags remain unchanged.
3. Send **explicit empty** → service runs an appropriate mutation to clear the collection → reads back empty.
4. Send **explicit null** → service deletes the column per contract → may also read back empty; check a state marker if distinction is required.

Never assert that “CQL empty” and “CQL null” always deserialize to two different Java values after round-trip.

### 7.4. CQL Collections Reject Null Elements

A CQL collection **cannot hold null elements**. Do not confuse **whole column = NULL** with **an element inside a list/map = NULL**:

~~~text
tags = NULL         -> column-level effect, can delete data
tags = {'a','b'}    -> valid set
tags = {'a',NULL}   -> invalid CQL set
aliases = [NULL]    -> invalid CQL list
quotas = {'x':NULL} -> invalid map value
~~~

Negative tests should construct a Java `List`/`Map` **actually containing null**, noting the exception may come from the codec before hitting the network or from the server. Assertions should confirm the mutation is rejected and **the existing row stays unchanged**, without matching error text character-for-character.

### 7.5. Set Duplicates, Map Duplicate Keys, List Duplicates

| Input | Test Expectation | Explanation |
|---|---|---|
| `Set.of("a","a")` | Java throws before binding | Java immutable factory rejects duplicates |
| `new HashSet<>(List.of("a","a"))` | Single element result | Set deduplicates |
| `List.of("a","a")` | Two elements | List preserves duplicates |
| Map puts same key twice | Only last value in Java Map | Map forbids duplicate keys |

**Never** pass an input rejected by a Java constructor and report “Cassandra rejected the duplicate”. Separate Java collection construction errors, codec errors, and server errors.

## 8. Collection Mutations, Frozen Collections, and Idempotency

### 8.1. Adding/Removing Elements Instead of Overwriting Everything

For non-frozen collections:

~~~sql
UPDATE it_lab.profile_by_id
SET tags = tags + {'verified'}
WHERE profile_id = 11111111-1111-4111-8111-111111111111;

UPDATE it_lab.profile_by_id
SET tags = tags - {'obsolete'}
WHERE profile_id = 11111111-1111-4111-8111-111111111111;

UPDATE it_lab.profile_by_id
SET quotas['daily'] = 42
WHERE profile_id = 11111111-1111-4111-8111-111111111111;

UPDATE it_lab.profile_by_id
SET aliases = aliases + ['new-alias']
WHERE profile_id = 11111111-1111-4111-8111-111111111111;
~~~

These mutations require a valid row/partition; if the row does not exist yet, Cassandra may upsert depending on the statement. Adding to a set has different semantics than **list append**:

- Adding the same element to a set does not create duplicates.
- Appending the same value to a list twice **can store two elements**, so retrying after a timeout can introduce duplicates.
- Updating a map entry by key overwrites that key; write timestamps/concurrency decide the winner.
- Certain list operations require read-before-write, carrying significant latency impact.

### 8.2. Mini Idempotency Test

~~~java
UUID id = UUID.randomUUID();
session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, tags, aliases) VALUES (?, ?, ?)")
    .bind(id, Set.of("a"), List.of("a")));

PreparedStatement addToSet = session.prepare(
    "UPDATE it_lab.profile_by_id SET tags = tags + ? " +
    "WHERE profile_id = ?");
PreparedStatement appendList = session.prepare(
    "UPDATE it_lab.profile_by_id SET aliases = aliases + ? " +
    "WHERE profile_id = ?");

// Run twice intentionally to observe the difference.
session.execute(addToSet.bind(Set.of("b"), id));
session.execute(addToSet.bind(Set.of("b"), id));
session.execute(appendList.bind(List.of("b"), id));
session.execute(appendList.bind(List.of("b"), id));

Row r = session.execute(session.prepare(
    "SELECT tags, aliases FROM it_lab.profile_by_id " +
    "WHERE profile_id=?").bind(id)).one();

org.junit.jupiter.api.Assertions.assertEquals(
    Set.of("a","b"), r.getSet("tags", String.class));
org.junit.jupiter.api.Assertions.assertEquals(
    List.of("a","b","b"), r.getList("aliases", String.class));
~~~

Sequential writes may occur with distinct timestamps. If tests override clocks/timestamps, account for conflict resolution. **Never** use set deduplication as an excuse to enable infinite retries: TTLs, side effects, and multi-replica failures still matter.

### 8.3. Frozen vs Non-Frozen Collections

Given:

~~~sql
CREATE TABLE it_lab.frozen_collection_by_id (
  id uuid PRIMARY KEY,
  tags frozen<set<text>>
);
~~~

`frozen<set<text>>` stores the collection as **a single value**. Updating “add one element” requires read/modify/write of the entire collection or a different schema; you cannot use the same partial-mutation operators as non-frozen collections. Under concurrent writers, whole-value replacement risks lost updates. Tests for frozen vs non-frozen must use separate tables/columns and never compare latency using a single row.

### 8.4. Nested Collections, UDTs, and `GenericType`

With nested generics, the Java Driver cannot express the type with `String.class` alone:

~~~java
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<Set<List<String>>> nested =
    new GenericType<Set<List<String>>>() {};

// Given a matching nested CQL schema frozen as required:
// Set<List<String>> value = row.get("nested_column", nested);
~~~

Write dedicated tests for:

- Type mismatches: Java `Map<String, Long>` does not silently become `map<text,int>`.
- Nested element codecs, frozen inner types, and map keys/values.
- Very large collections: test **input limits/validation** rather than stuffing hundreds of MB into one row.
- Collection mutation with TTLs; per-cell/element TTLs in a non-frozen collection must not be misread as one single deadline for the whole collection.

## 9. UDTs: Creating, Writing, Reading, and NULL Fields

### 9.1. UDTs Have a Schema, Not Arbitrary Maps

`it_lab.address_info` has three exact fields in schema order:

~~~sql
CREATE TYPE it_lab.address_info (
  street text,
  city text,
  postal_code text
);
~~~

`UdtValue` is created from Cassandra/Driver metadata—**never construct a `UserDefinedType` manually with arbitrary fields**, because a UDT schema includes exact field names and order. If reusing an object from another `CqlSession` or across schema changes, verify type attachment, metadata, and codecs.

### 9.2. Creating `UdtValue` from Schema Metadata

~~~java
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

UserDefinedType addressType = session.getMetadata()
    .getKeyspace("it_lab")
    .flatMap(ks -> ks.getUserDefinedType("address_info"))
    .orElseThrow(() -> new IllegalStateException("UDT not loaded"));

UdtValue home = addressType.newValue()
    .setString("street", "12 Lê Lợi")
    .setString("city", "Đà Nẵng")
    .setString("postal_code", "550000");

PreparedStatement write = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, home) VALUES (?, ?)");

UUID id = UUID.randomUUID();
session.execute(write.bind().setUuid(0, id).setUdtValue(1, home));

Row r = session.execute(session.prepare(
    "SELECT home FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(r);
UdtValue actual = r.getUdtValue("home");
org.junit.jupiter.api.Assertions.assertNotNull(actual);
org.junit.jupiter.api.Assertions.assertEquals(
    "Đà Nẵng", actual.getString("city"));
org.junit.jupiter.api.Assertions.assertEquals(
    "550000", actual.getString("postal_code"));
~~~

`home` in the schema is `frozen<address_info>`; on write, the entire object is treated as one value. `UdtValue` in Driver 4.x is **mutable** by default, while `BoundStatement` is immutable. Never share a mutable `UdtValue` across concurrent writing threads without copying.

### 9.3. UDTs with Missing Fields Read Back as Null

~~~java
UdtValue partial = addressType.newValue()
    .setString("city", "Huế");
// Do not set street and postal_code.

UUID id2 = UUID.randomUUID();
session.execute(write.bind().setUuid(0, id2).setUdtValue(1, partial));

UdtValue readBack = session.execute(session.prepare(
    "SELECT home FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id2)).one().getUdtValue("home");

org.junit.jupiter.api.Assertions.assertEquals(
    "Huế", readBack.getString("city"));
org.junit.jupiter.api.Assertions.assertTrue(readBack.isNull("street"));
org.junit.jupiter.api.Assertions.assertTrue(readBack.isNull("postal_code"));
~~~

A CQL UDT literal can omit fields; omitted parts become NULL. **Do not treat a missing field inside a frozen UDT like “UNSET on an outer column”**: writing a new frozen UDT replaces the whole value and wipes old fields. Therefore, tests mapping partial DTO updates → frozen UDTs must clarify whether business logic requires “replace” or “merge”.

## 10. Frozen UDTs vs Non-Frozen UDTs

### 10.1. Difference at the Mutation Unit

| Property | `home frozen<address_info>` | `office address_info` |
|---|---|---|
| Storage | Single value representing the whole UDT | Fields can be stored as separate cells |
| Update `column.city = ?` | Does **not** support partial field updates | Supports CQL field updates |
| Writing full object | Replaces whole UDT; can wipe omitted fields | Affects set fields per statement |
| TTL/tombstones | Whole-value semantics | Can apply to individual fields/cells |
| Concurrency | Whole-value replacement risks lost updates on stale DTOs | Field-specific writes reduce accidental conflicts; still not a cross-partition ACID transaction |

### 10.2. Updating One Field of a Non-Frozen UDT

~~~java
UUID id = UUID.randomUUID();
UserDefinedType addressType = session.getMetadata()
    .getKeyspace("it_lab")
    .flatMap(ks -> ks.getUserDefinedType("address_info"))
    .orElseThrow();

UdtValue office = addressType.newValue()
    .setString("street", "1 Main St")
    .setString("city", "Hanoi")
    .setString("postal_code", "100000");

session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id (profile_id, office) " +
    "VALUES (?, ?)").bind(id, office));

PreparedStatement changeCity = session.prepare(
    "UPDATE it_lab.profile_by_id SET office.city = ? " +
    "WHERE profile_id = ?");
session.execute(changeCity.bind("Hai Phong", id));

UdtValue after = session.execute(session.prepare(
    "SELECT office FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one().getUdtValue("office");

org.junit.jupiter.api.Assertions.assertEquals(
    "Hai Phong", after.getString("city"));
org.junit.jupiter.api.Assertions.assertEquals(
    "1 Main St", after.getString("street"));
org.junit.jupiter.api.Assertions.assertEquals(
    "100000", after.getString("postal_code"));
~~~

On a **frozen UDT**, the equivalent `SET home.city = ?` query must be rejected. Write a separate negative test and assert semantic rejection only, without relying on exact message text:

~~~java
org.junit.jupiter.api.Assertions.assertThrows(
    com.datastax.oss.driver.api.core.servererrors.InvalidQueryException.class,
    () -> session.execute(
        "UPDATE it_lab.profile_by_id SET home.city = 'Hue' " +
        "WHERE profile_id = 11111111-1111-4111-8111-111111111111"));
~~~

Negative tests may throw during prepare or execute depending on the API call, so wrap **the entire call** inside the assertion lambda.

### 10.3. UDT Evolution and Mapping Compatibility

If you alter a UDT with:

~~~sql
ALTER TYPE it_lab.address_info ADD country text;
~~~

tests must verify:

1. Driver **schema metadata** refreshes before binding/reading objects with the new field.
2. Older data lacking `country` is read with compatible/null semantics.
3. New code knows `country` while old code continues running during rollbacks/mixed versions per protocol/schema support.
4. UDT field order/names are never guessed or constructed via detached types incompatible with the schema.
5. Migrations/versions are pinned; avoid running `ALTER TYPE` on a shared schema while parallel test classes execute.

**Never run `ALTER TYPE` inside basic tests sharing `profile_by_id`**, as it can break prepared statements and concurrent tests expecting the prior schema. Use a **dedicated keyspace or container** for schema-evolution tests.

## 11. Boundary Values for Integers, Decimals, and Booleans

### 11.1. CQL Types and Java Types Must Match Exactly

| CQL Type | Java Driver Type/API | Boundary Tests |
|---|---|---|
| `tinyint` | `byte` / `setByte` / `getByte` | -128, 0, 127; 128 **out of range** |
| `smallint` | `short` / `setShort` / `getShort` | -32768, 32767; 32768 **out of range** |
| `int` | `int` / `setInt` / `getInt` | `Integer.MIN_VALUE/MAX_VALUE` |
| `bigint` | `long` / `setLong` / `getLong` | `Long.MIN_VALUE/MAX_VALUE` |
| `varint` | `BigInteger` / `setBigInteger` / `getBigInteger` | Numbers larger than `Long.MAX_VALUE` |
| `decimal` | `BigDecimal` / `setBigDecimal` / `getBigDecimal` | Scale, negative, 0, long fractional parts |
| `boolean` | `boolean` / `setBoolean` / `getBoolean` | `true/false` and distinguishing NULL via `isNull` |

**Never use Java `int` to read a CQL `varint`.** Manual conversion via `longValue()` silently truncates out-of-range values. Never compare decimals with `double` if business logic needs exact money or quantity precision.

### 11.2. Round-Tripping Multiple Boundary Types in One Row

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.UUID;

UUID id = UUID.randomUUID();
BigInteger huge = new BigInteger("18446744073709551617000");
BigDecimal amount = new BigDecimal("-1234567890.000100");

PreparedStatement write = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, priority_tiny, short_value, score, " +
    "long_value, huge_value, amount, active) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)");

BoundStatement bs = write.bind()
    .setUuid(0, id)
    .setByte(1, Byte.MIN_VALUE)
    .setShort(2, Short.MAX_VALUE)
    .setInt(3, Integer.MIN_VALUE)
    .setLong(4, Long.MAX_VALUE)
    .setBigInteger(5, huge)
    .setBigDecimal(6, amount)
    .setBoolean(7, false);
session.execute(bs);

Row r = session.execute(session.prepare(
    "SELECT priority_tiny, short_value, score, long_value, " +
    "huge_value, amount, active FROM it_lab.profile_by_id " +
    "WHERE profile_id=?").bind(id)).one();

org.junit.jupiter.api.Assertions.assertNotNull(r);
org.junit.jupiter.api.Assertions.assertEquals(
    Byte.MIN_VALUE, r.getByte("priority_tiny"));
org.junit.jupiter.api.Assertions.assertEquals(
    Short.MAX_VALUE, r.getShort("short_value"));
org.junit.jupiter.api.Assertions.assertEquals(
    Integer.MIN_VALUE, r.getInt("score"));
org.junit.jupiter.api.Assertions.assertEquals(
    Long.MAX_VALUE, r.getLong("long_value"));
org.junit.jupiter.api.Assertions.assertEquals(
    huge, r.getBigInteger("huge_value"));
org.junit.jupiter.api.Assertions.assertEquals(
    0, amount.compareTo(r.getBigDecimal("amount")));
org.junit.jupiter.api.Assertions.assertFalse(r.getBoolean("active"));
org.junit.jupiter.api.Assertions.assertFalse(r.isNull("active"));
~~~

`BigDecimal.compareTo` compares numeric value; `BigDecimal.equals` also checks **scale**. If the business contract mandates a fixed scale, add an `actual.scale()` assertion after confirming Cassandra/codecs preserve scale, rather than relying solely on `compareTo`. When rendering JSON, `BigDecimal` serialization may alter notation; test HTTP mapping too.

### 11.3. NULL for Numbers or Booleans Is Not `0`/`false`

~~~java
// Suppose score and active have not been written yet:
Row r = session.execute(session.prepare(
    "SELECT score, active FROM it_lab.profile_by_id " +
    "WHERE profile_id=?").bind(id)).one();

// r is non-null only if id actually has a live row.
if (r != null) {
    Integer score = r.isNull("score") ? null : r.getInt("score");
    Boolean active = r.isNull("active") ? null : r.getBoolean("active");
}
~~~

With Java primitive getters, CQL NULL turns into defaults (`0`/`false`); **always check `Row.isNull`** when business logic separates “unknown” from `false`/`0`. Never assert `getInt()==0` to prove the column stores `0` without checking `isNull`.

### 11.4. Overflow and Type-Mismatch Tests Must Hit the Right Layer

For instance, CQL literal `priority_tiny = 128` is out of `tinyint` range and should be rejected by parser/validation. If Java evaluates `(byte) 128`, it **already wraps to -128 before reaching the driver**—an integration test passing `-128` does not prove Cassandra accepts `128`.

Test:

~~~java
// Java cast overflows before binding; DO NOT use to test server range.
byte wrapped = (byte) 128; // -128

// Test server-side CQL literal using a valid UUID and a lab table:
// INSERT INTO it_lab.profile_by_id
//   (profile_id, priority_tiny)
// VALUES (11111111-1111-4111-8111-111111111111, 128);
// Expect rejection because the value does not fit tinyint.
~~~

Similarly, a huge Java `BigInteger` **remains valid for CQL `varint`** within real codec/storage bounds, yet cannot be cast down to `long`. Tests must separate **server acceptance**, **driver codecs**, and **DTO serialization**.

## 12. Temporal Types, Unicode, `blob`, and `inet`

### 12.1. Timestamp: Understanding Units and Precision

CQL `timestamp` stores **milliseconds** since the Unix epoch, whereas Java `Instant` supports **nanoseconds**. A higher-precision `Instant` is truncated/rounded to milliseconds when written through the codec.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;

UUID id = UUID.randomUUID();
Instant withNanos = Instant.parse(
    "1969-12-31T23:59:59.123456789Z");
Instant expectedStored =
    Instant.ofEpochMilli(withNanos.toEpochMilli());

LocalDate leapDay = LocalDate.of(2000, 2, 29);
LocalTime lastNano = LocalTime.of(23, 59, 59, 999_999_999);

PreparedStatement ps = session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, created_at, event_day, event_time) " +
    "VALUES (?, ?, ?, ?)");
session.execute(ps.bind()
    .setUuid(0, id)
    .setInstant(1, withNanos)
    .setLocalDate(2, leapDay)
    .setLocalTime(3, lastNano));

Row r = session.execute(session.prepare(
    "SELECT created_at, event_day, event_time " +
    "FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();

org.junit.jupiter.api.Assertions.assertEquals(
    expectedStored, r.getInstant("created_at"));
org.junit.jupiter.api.Assertions.assertEquals(
    leapDay, r.getLocalDate("event_day"));
org.junit.jupiter.api.Assertions.assertEquals(
    lastNano, r.getLocalTime("event_time"));
~~~

**Especially before 1970:** use `toEpochMilli()` instead of hand-rolled `Instant.getEpochSecond() * 1000 + getNano()/1_000_000` math that mishandles negative epochs. `timestamp` stores an absolute instant **without a timezone ID**: timezones belong to application-side parsing/formatting.

### 12.2. Distinguishing `date`, `time`, and `timestamp`

| CQL Type | Java Type | What to Test |
|---|---|---|
| `date` | `LocalDate` | Leap day, pre-1970, timezone-free calendar date |
| `time` | `LocalTime` | 00:00:00, 23:59:59.999999999, nanoseconds |
| `timestamp` | `Instant` | Pre/post-epoch, millisecond precision, UTC display |
| `duration` | `CqlDuration` | **Months/days/nanos**; never assume fixed-second `Duration` conversion |
| `timeuuid` | Version-1 UUID | Never generate a v4 `UUID.randomUUID()` and bind as `timeuuid` |

For `duration`, a month is not always 30 days. If a Java API uses `java.time.Duration` to represent “1 month”, design an explicit converter rather than treating all durations as fixed milliseconds. For `timeuuid`, test version/time ordering compatibility rather than lexical UUID string sorting.

### 12.3. Unicode and Empty Strings

~~~java
import java.text.Normalizer;

String composed = "Café 🚀";
String decomposed = "Cafe\u0301 🚀";

org.junit.jupiter.api.Assertions.assertNotEquals(
    composed, decomposed);  // Distinct Unicode code point sequences.

String normalized =
    Normalizer.normalize(decomposed, Normalizer.Form.NFC);
org.junit.jupiter.api.Assertions.assertEquals(composed, normalized);
~~~

When round-tripping `text/varchar`:

- Test Vietnamese diacritics, emojis (Java surrogate pairs), combining characters, length 0, and multi-byte UTF-8 strings.
- Never assume Cassandra/codecs **auto-normalize Unicode** to NFC/NFD or perform case-insensitive comparisons.
- If business rules require accent/case-insensitive usernames, normalize/case-fold and store a dedicated key **before binding**; keep one consistent policy system-wide.
- Never equate `String.length()` with Unicode code point count or UTF-8 byte length: all three differ.

### 12.4. `blob`: `ByteBuffer` Has `position` and `limit`

~~~java
import java.nio.ByteBuffer;
import java.util.Arrays;

byte[] payload = new byte[] {0, 1, 0, (byte) 0xFF};
ByteBuffer original = ByteBuffer.wrap(payload);
UUID id = UUID.randomUUID();

session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, blob_value) VALUES (?, ?)")
    .bind(id, original));

Row r = session.execute(session.prepare(
    "SELECT blob_value FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();

ByteBuffer buffer = r.getByteBuffer("blob_value");
org.junit.jupiter.api.Assertions.assertNotNull(buffer);
ByteBuffer copy = buffer.duplicate();
byte[] actual = new byte[copy.remaining()];
copy.get(actual);

org.junit.jupiter.api.Assertions.assertArrayEquals(payload, actual);
~~~

`ByteBuffer.get(...)` advances the buffer's **position**; use `duplicate()` or `asReadOnlyBuffer()` whenever multiple readers inspect it. Never coerce arbitrary binary data to UTF-8 text for string comparison when payloads contain zero bytes or invalid byte sequences.

### 12.5. `inet` and DNS

~~~java
import java.net.InetAddress;

InetAddress localhostIPv4 = InetAddress.getByAddress(
    new byte[] {127, 0, 0, 1});

UUID id = UUID.randomUUID();
session.execute(session.prepare(
    "INSERT INTO it_lab.profile_by_id " +
    "(profile_id, source_ip) VALUES (?, ?)")
    .bind(id, localhostIPv4));

Row r = session.execute(session.prepare(
    "SELECT source_ip FROM it_lab.profile_by_id WHERE profile_id=?")
    .bind(id)).one();
org.junit.jupiter.api.Assertions.assertEquals(
    localhostIPv4, r.getInetAddress("source_ip"));
~~~

Use `InetAddress.getByAddress` so tests do not depend on DNS. For IPv6, pass 16 raw bytes. Never assert rendered IP strings match input verbatim (IPv6 has multiple valid text forms). If an API accepts hostnames, DNS resolution is separate logic requiring its own tests/deterministic stubs.

## 13. Spring Data, Mappers, and Application-Layer Null Contracts

### 13.1. Two Mapping Layers Must Be Tested Separately

**Direct Java Driver:** tests explicitly show `bind()`/`setToNull()`/`unset()` and `Row`. **Spring Data Cassandra / Java Driver Mapper:** converter/DAO layers may enforce a different null-saving strategy. A passing raw-driver test **does not prove** entity mapping handles `null` the way your PATCH API intends.

For example, Apache Java Driver Mapper 4.19 provides `NullSavingStrategy`:

| Mapper Strategy | When Entity Property Is Null | Effect |
|---|---|---|
| `DO_NOT_SET` (Mapper annotation default unless overridden) | Skips setter on bind variable | Column stays UNSET; preserves old value |
| `SET_TO_NULL` | Calls setter with null | CQL NULL; may create tombstone and delete old value |

~~~java
// Illustrative Java Driver Mapper 4.x annotation only:
//
// @Dao
// interface ProfileDao {
//     @Update(nullSavingStrategy = NullSavingStrategy.SET_TO_NULL)
//     void updateAllowNullDelete(ProfileEntity entity);
// }
~~~

**Do not equate with Spring Data Cassandra:** Spring Data `CassandraTemplate` has its own converters, write options, and version-specific behavior. Test **the exact code path** used by your service, e.g.:

1. Seed `note="old"` via raw CQL.
2. Call repository/`CassandraOperations.update(entity)` with `note=null`.
3. Read back via raw CQL to verify whether `note` stayed or was deleted.
4. Adjust policy/options if required by the contract; record exact config/version in tests.
5. Inspect TTL/`WRITETIME` when proving unrelated columns were untouched.

### 13.2. PATCH JSON Must Preserve All Three States

If a DTO uses a plain `String note`:

~~~json
{}
~~~

and:

~~~json
{ "note": null }
~~~

both deserialize to `note=null` in Java, **losing field-presence information**. To support PATCH properly:

- Use a wrapper/tri-state field presence type, `JsonNode`, or structure tracking “was provided”.
- Absent → **UNSET** in prepared UPDATE.
- Explicit null → **`setToNull`** when business rules mean clear.
- Non-null string (including empty) → **`setString`**.
- Write HTTP → CQL integration tests for all three cases, not just DTO parsing tests.

### 13.3. `Optional` Is Not a Complete Solution

`Optional.empty()` cannot distinguish an absent field from explicit null if the serializer/framework maps both to empty. Where business logic has three states, track **two pieces of information**—presence flag and value—or an explicit algebraic type:

~~~text
PatchField =
  Absent
  | Clear
  | Set(value)

mapping:
  Absent -> BoundStatement.unset(...)
  Clear  -> BoundStatement.setToNull(...)
  Set(x) -> BoundStatement.setXxx(...)
~~~

In reactive/async code, `BoundStatement` is immutable and safe to pass across threads per driver semantics, whereas **builders** and default `UdtValue` instances are mutable and must not be mutated concurrently.

### 13.4. Do Not Test Tombstones by Counting SSTable Files Directly

To measure null-saving performance impact, run a dedicated **soak/integration benchmark**:

- Issue many updates with explicit NULL vs UNSET.
- Measure tombstones scanned and compaction using release-appropriate tools.
- Compare SSTable footprint and read p95/p99 over a realistic window.
- Hold replication, repair, TTL, `gc_grace_seconds`, and dataset constant.

Never run a 2-row JUnit test and claim “NULL creates exactly one visible tombstone in SSTables”; the storage engine and compaction are not that simplistic.

## 14. Layer-Accurate Assertions: Codec, CQL, Server, and Business

### 14.1. Test Error Matrix

| Scenario | Where Can It Be Rejected? | Recommended Assertion |
|---|---|---|
| `UUID.randomUUID()` bound to `timeuuid` | Driver codec/serialization or server | Error type and row not written |
| Java `byte` cast from 128 | **Java** already overflowed | Validate at HTTP/DTO layer before casting |
| NULL inside collection element | Driver codec or server | Reject input and keep old row intact |
| Non-existent UDT field name | Driver setter or server | Reject and verify schema compatibility |
| `home.city` on frozen UDT | Server CQL validation | `InvalidQueryException`/semantic rejection |
| PK NULL or UNSET | Driver/server | Mutation never accepted as valid |
| Query missing partition key | Server query validation | Never enable ALLOW FILTERING to “pass” |
| `bigint` value into `int` column | Codec/type mismatch or server | Never silently truncate data |
| Timeout/lost ACK on write | Driver/server/network | **UNKNOWN outcome**; never assume rollback |
| LWT IF condition unmet | CQL returns `[applied]=false` | **Not an exception**; check `wasApplied()` |

**“Business rejections” and “infrastructure errors” must stay distinct:** LWT false is a conditional conflict; a timeout may happen after the write already applied. When injecting timeouts on non-idempotent collection updates, reconcile and check for duplicates rather than retrying blindly.

### 14.2. Verifying State After Rejection

Negative test pattern:

~~~text
given: row note='stable', score=7
when: send invalid mutation (NULL PK / invalid collection element)
then: request rejected
and: SELECT by valid PK still returns note='stable', score=7
and: no partial business side effects are claimed
~~~

Never assert only the exception and skip checking data integrity. For multi-partition batches/ETLs, a failure may leave partial components applied under different semantics; test transaction scope separately.

### 14.3. Do Not “Snapshot” `cqlsh` Output in Tests

`cqlsh` formats `null`, collection ordering, timestamps, and decimals for display; formatting can change across versions. Instead:

- Use typed getters: `getInt/getBigDecimal/getList/getUdtValue/getInstant`.
- Use `isNull` for scalar primitives.
- For binary, compare byte arrays rather than rendered hex strings unless required by contract.
- For maps/sets, compare element equality, not iteration order.
- For `BigDecimal`, separate numeric equality from business scale.
- For temporal types, assert exact precision and timezone semantics.

### 14.4. Controlling Races, TTL, and Timestamps

A test like:

~~~text
UPDATE note='A'
UPDATE note=NULL
SELECT note expected NULL
~~~

is reliable only when both mutations execute and are observed in a controlled order with proper clock/timestamp semantics. Cassandra resolves conflicts via timestamps; assigning identical timestamps to two mutations can make results independent of statement order. Avoid manual write timestamps in standard NULL/UNSET tests.

For TTLs, use fake clocks/service-level abstractions where possible; **never sleep exactly one second asserting TTL expired**, as scheduling, networking, and reconciliation cause flakiness. When testing real TTLs, poll within a bounded timeout window with an explicit deadline.

## 15. Complete Test Case Matrix and Data Management

| Group | Input | Expected Result | Condition to Assert |
|---|---|---|---|
| NULL vs UNSET | note UNSET, score=8 | note preserved, score=8 | Seed note beforehand |
| NULL vs UNSET | note NULL, score UNSET | note null, score unchanged | Row still alive |
| Scalar empty | note = `""` | note non-null, length 0 | No service-level normalization |
| PK absent | profile_id UNSET/NULL | Request rejected | Driver/server validation active |
| Collection set | `{"a","b"}` | No duplicates, order-agnostic | Built-in codec |
| Collection list | `["a","a"]` | Preserves both elements and order | Standard mutation only |
| Collection map | `{"a":0,"b":-1}` | Exact keys/values match | CQL `map<text,int>` |
| Collection empty | `[]`/`{}` | Getter may return empty; null distinction unguaranteed | Document codec/version |
| Collection invalid | Null element | Rejected and old row untouched | Check appropriate error |
| Collection retry | Append list twice | Duplicates genuinely possible | No concurrent writers |
| Frozen UDT | Write full `UdtValue` | Round-trips field names/types | Accurate type metadata |
| Frozen UDT | SET `home.city` | Rejected | Frozen field mutation unsupported |
| Non-frozen UDT | SET `office.city` | Only city changes, other fields intact | Seed all fields |
| UDT partial | Omit street/postal_code | Missing fields read back null | Whole UDT written |
| Tinyint/smallint | Min/max | Exact typed round-trip | No pre-test Java cast |
| Varint/decimal | > `Long.MAX`, large scale | Exact `BigInteger`/`BigDecimal` | Never convert via `double` |
| Timestamp | Pre-epoch + nanoseconds | Accurate to milliseconds | Matching codec release |
| Date/time | Leap day, end-of-day nanos | Exact `LocalDate`/`LocalTime` | Timezone-free test |
| Unicode | NFC/NFD, Vietnamese, emoji | Bound text preserved without auto-normalization | Compare code points when needed |
| Blob | Contains `0x00`/`0xFF` | Byte arrays equal | Duplicate `ByteBuffer` |
| Inet | IPv4/IPv6 bytes | Addresses equal | DNS-independent |

### 15.1. Test Isolation and Cleanup

- Each test uses a fresh `UUID.randomUUID()`; when testing ordering/retries on the same PK, scope that PK **strictly within one test**.
- Never share hardcoded UUIDs across test classes running in parallel.
- Create the schema once per container using isolated fixtures; avoid constantly creating/dropping types across concurrent tests.
- Keep one container per class to cut startup overhead; never enable container reuse across CI runs without explicit state management.
- Let container lifecycle handle teardown cleanup; per-row `DELETE`s generate tombstones that can skew benchmarks.
- Never share prepared statement builders or mutable `UdtValue` instances across threads building mutations concurrently.
- Record image name, Cassandra version, driver, Testcontainers, OS/arch, native protocol, and test seeds in failure reports.

## 16. Complete JUnit Integration Test for NULL/UNSET

Earlier snippets isolated individual experiments. Below is a **self-contained test method** you can place inside `CassandraTypesIT` from Section 3 (after `@BeforeAll` creates the keyspace, UDT, and table from Section 4):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

// Inside CassandraTypesIT, with field "session" initialized:
@Test
void unsetPreservesValueButNullDeletesIt() {
    UUID id = UUID.randomUUID();

    PreparedStatement seed = session.prepare(
        "INSERT INTO it_lab.profile_by_id " +
        "(profile_id, note, score) VALUES (?, ?, ?)");
    session.execute(seed.bind(id, "initial", 5));

    PreparedStatement patch = session.prepare(
        "UPDATE it_lab.profile_by_id " +
        "SET note = ?, score = ? WHERE profile_id = ?");
    PreparedStatement read = session.prepare(
        "SELECT note, score FROM it_lab.profile_by_id " +
        "WHERE profile_id = ?");

    // Patch 1: omit note -> UNSET; update score only.
    BoundStatement preserve = patch.bind()
        .setInt(1, 6)
        .setUuid(2, id);
    assertFalse(preserve.isSet(0));
    session.execute(preserve);

    Row first = session.execute(read.bind(id)).one();
    assertNotNull(first);
    assertEquals("initial", first.getString("note"));
    assertEquals(6, first.getInt("score"));

    // Patch 2: explicitly clear note, leaving score UNSET.
    BoundStatement clear = patch.bind()
        .setToNull(0)
        .setUuid(2, id);
    assertTrue(clear.isSet(0));
    assertFalse(clear.isSet(1));
    session.execute(clear);

    Row second = session.execute(read.bind(id)).one();
    assertNotNull(second);
    assertTrue(second.isNull("note"));
    assertEquals(6, second.getInt("score"));

    // Patch 3: empty string is a value, not NULL.
    session.execute(patch.bind()
        .setString(0, "")
        .setUuid(2, id));
    Row third = session.execute(read.bind(id)).one();
    assertNotNull(third);
    assertFalse(third.isNull("note"));
    assertEquals("", third.getString("note"));
    assertEquals(6, third.getInt("score"));
}
~~~

**Why this test is relatively stable:** it uses a fresh UUID, executes mutations sequentially, and reads back with a prepared SELECT on the same session without relying on `cqlsh` text formatting of `null` or numbers. It does not require a multi-node cluster to prove NULL/UNSET semantics.

**Limitations:** the class scaffold covers only core setup; running the full suite requires Gradle/Maven, JUnit Jupiter, Testcontainers, Java Driver, a Docker runtime, and properly ordered schema setup. Network failure/repair/CL tests require separate **multi-node** fixtures.

### 16.1. Standardizing Setup and Test Data Factories

In larger projects, extract helpers:

~~~java
// Example helper signatures; separate files are not required in this lesson:
// UUID newProfileWithNote(String note);
// Row readProfile(UUID profileId);
// PreparedStatement patchProfileStatement();
// UdtValue address(String street, String city, String zip);
// void assertNoUnexpectedMutation(UUID id, ExpectedState expected);
~~~

Prepare statements once after schema readiness and reuse them; avoid running schema DDL per test case or altering UDTs mid-suite. Helpers must **never** swallow exceptions or auto-retry bind/codec errors, as that hides the bugs tests are meant to catch.

### 16.2. Parameterized Tests per Value Class

JUnit 5 provides `@ParameterizedTest` and `@MethodSource`. A data provider can yield:

~~~java
import java.util.stream.Stream;
import org.junit.jupiter.params.provider.Arguments;

static Stream<Arguments> scoreCases() {
    return Stream.of(
        Arguments.of(Integer.MIN_VALUE),
        Arguments.of(-1),
        Arguments.of(0),
        Arguments.of(1),
        Arguments.of(Integer.MAX_VALUE)
    );
}
~~~

Test each value with a **fresh UUID**, call `setInt/getInt` on the exact column, and assert `!row.isNull("score")` before comparing. When using property-based testing (jqwik/QuickTheories), pin the random seed on failure and log **only non-sensitive fixture data**, never user rows.

### 16.3. Test Framework Issues with External Resources

A Java/Maven test run can fail for non-Cassandra reasons:

- Docker socket/runtime is down or CI disallows starting containers.
- Docker image pull blocked by network/registry rate limits.
- Insufficient RAM/CPU causing slow Cassandra startup or OOM-kills.
- Node advertised address unreachable from the test process (Docker-in-Docker/remote daemon).
- Native port blocked or truststore/auth unconfigured.
- Mixed Testcontainers 1.x and 2.x packages/artifacts causing `ClassNotFoundException`.

In reports, separate **`ENVIRONMENT_SETUP_FAILURE`** from **`CQL_SEMANTIC_FAILURE`**; never mislabel an environment failure as “NULL column broken” or mass-skip tests without documented reasons.

## 17. CI Matrix by Version and Topology

### 17.1. Single Node Suffices for Data Types, Not Replication

| Test Class | Cassandra 4.1, 1 Node | Cassandra 5.0, 1 Node | Multi-Node |
|---|---|---|---|
| NULL vs UNSET protocol V4+ | **Mandatory** | Mandatory if release supported | Usually unneeded to prove semantics |
| CQL PK null/unset validation | Mandatory | Mandatory | Unneeded |
| Collections list/set/map | Mandatory | Mandatory | Can add replica fault coverage |
| Frozen/non-frozen UDTs | Mandatory | Mandatory | Can add schema agreement coverage |
| Scalar boundaries, date/time/blob | Mandatory | Mandatory | Unneeded |
| Spring Data converters/mappers | Mandatory for stack used | Mandatory when upgrading | Unneeded for basic mapping |
| `LOCAL_QUORUM` availability | **Unsuitable** with RF1 | Unsuitable with RF1 | **Mandatory** |
| Node outage/repair/hinted handoff | Inconclusive | Inconclusive | **Mandatory** |
| LWT contention/multi-DC serial CL | Insufficient | Insufficient | **Mandatory** |

When upgrading Cassandra or the Driver:

1. Pin identical schemas/fixtures and compare assertions across versions.
2. Read CQL/protocol/codec release notes rather than assuming unchanged behavior.
3. Inspect schema metadata after `ALTER TYPE` and stale prepared statements.
4. Test DTO serialization across HTTP/Kafka/snapshots if applicable.
5. Document every expected behavioral change requiring migrations or feature flags.

### 17.2. Testcontainers and CI Runtime Budget

Cassandra container startup is not as fast as an in-memory database:

- Separate fast unit tests from containerized integration tests.
- Allow caching valid Docker images while pinning digests per security policy.
- Provision adequate CPU/RAM so Cassandra avoids OOMs and aggressive GC pauses.
- Run the Testcontainers extension sequentially when sharing a static container and schema.
- Never enable 3x suite-wide CI retries to mask flaky tests; separate transient infra failures from correctness bugs.
- Collect logs, thread dumps/`cqlsh` status, and driver exceptions **on failure**, keeping credentials out of logs.

In Dockerless build environments, tests can target an ephemeral Cassandra cluster provisioned per CI job, provided there is **no production data**, strict isolation, cleanup, proper RF/CL, and schema-creation rights. Mocked drivers belong strictly in unit tests, never replacing data-type integration tests.

### 17.3. Testing Multi-Node Topologies

A cluster with RF=3 in `dc1` (at least three nodes) lets you test:

- Writing/reading at `LOCAL_QUORUM` with sufficient local replicas.
- Stopping one node in an authorized environment and observing `Unavailable`/timeouts per CL.
- Schema agreement after adding/altering UDT fields.
- TTL/tombstone reconciliation under repair/compaction in a dedicated lab.
- Hot partitions/skew and coordinator placement.

**Never** use a single-node NULL/UNSET test to claim data “replicated cluster-wide” or “survives node loss”. Its job is verifying **CQL semantics and Java codecs**.

## 18. Diagnosing Test Failures

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `NullPointerException` reading `Row` | SELECT found no row for PK | Assert row is non-null before getters |
| `getInt` returns 0 when expecting null | Primitive getter hides nullable semantics | Check `row.isNull("score")` |
| NULL preserves old column | Mapper uses `DO_NOT_SET` instead of `SET_TO_NULL` | Inspect generated statement/mapper config |
| UNSET deletes column | Bound wrong index/name, passed null to setter, or prior mutation ran | Assert `BoundStatement.isSet` and CQL bind order |
| Empty collection returns `List.of()` instead of null | Default driver codec maps empty/missing to empty | Adjust assertion; add marker if business requires distinction |
| Set order differs from test | Sets guarantee no ordering like Lists | Compare equality as Sets |
| List has duplicates after retry | List append is non-idempotent | Deduplicate/event ID; stop blind retries |
| UDT `getString("city")` unexpectedly null | Partial UDT, omitted field, or metadata mismatch | Inspect type fields and bound payload |
| SET frozen UDT field rejected | Field-level mutation unsupported | Replace full UDT or use non-frozen schema |
| UDT codec mismatch | `UdtValue` created from another session/schema | Fetch `UserDefinedType` from current session metadata |
| Tinyint 128 becomes -128 | Java byte cast overflowed before sending | Validate numbers before casting; test raw CQL literal |
| Timestamp precision skew | `Instant` nanos → CQL millis | Compare after truncating to milliseconds |
| Decimal equality fails despite equal value | Different scales | Use `compareTo` and assert scale separately if needed |
| Blob test fails after first read | `ByteBuffer` position advanced | Duplicate buffer before reading bytes |
| `InvalidQueryException` on PK UNSET | Expected validation error | Do not treat as retryable network failure |
| Timeout on UPDATE | May have written despite lost ACK | UNKNOWN outcome; reconcile before retrying |
| Testcontainers fails to start | Docker/RAM/image/port/wait strategy | Collect logs and environment diagnostics |
| Passes locally, fails in CI | Version drift, clock/locale, parallel state, resource limits | Pin versions, seeds, timezones; isolate tests |

### 18.1. Three Easily Confused Failure Categories

**Bind/codec errors:** Java object cannot serialize to the target CQL type—e.g., schema expects `Integer` in a map while service passes `Long`. Fix input/converters; do not retry.

**CQL validation errors:** server rejects null PK, frozen field update, or invalid partition predicate. Fix CQL/schema or validation; do not retry.

**Infrastructure/timeout errors:** request may or may not have executed; for mutations, handle unknown outcomes. Never treat a timeout as “operation definitely did not run” just to simplify test passes.

### 18.2. Which Tests Should Not Run on Every Pull Request?

Heavy-impact tests—continuous SSTable flushes, multi-node RF changes, repair/decommission, prolonged network chaos, million-cell tombstone benchmarks—belong in **nightly/soak/chaos pipelines** or staging labs rather than blocking every small PR. Core correctness tests for NULL/UNSET, collections, UDTs, and scalar boundaries should stay in regular CI.

## 19. Scenario Exercises

### Exercise 1 — Absent vs Explicit Null in PATCH

An app receives `{}` and `{"note":null}`. Both Java DTOs yield `note == null`. Why is this a latent bug?

**Answer:** **Field presence** information was lost. If the PATCH contract specifies absent = preserve and explicit null = delete, the DTO must preserve presence so UNSET and NULL can be bound differently.

### Exercise 2 — UNSET on a Row with Existing Data

A row has `note="x"`, `score=10`. CQL `UPDATE SET note=?, score=?` binds `note=UNSET`, `score=11`. Outcome?

**Answer:** `note` remains `"x"`, `score` becomes `11`. UNSET skips assignment without creating a tombstone for `note`.

### Exercise 3 — NULL on a Non-Key Column

A row has `note="x"` and `score=10`. Bind `note=NULL`, `score=UNSET`. Is the whole row deleted?

**Answer:** No. Only `note` is deleted while `score` stays `10`; the row remains readable via the remaining live cell. NULLs typically create tombstones, so monitor if repeated heavily.

### Exercise 4 — Empty vs Null Collection

Code sees `row.getList("aliases", String.class).isEmpty()`. Does this prove the client sent `[]` rather than never sending `aliases`?

**Answer:** No. Cassandra/built-in codecs may not distinguish those two states on read. Preserving that business distinction requires a separate marker/state column.

### Exercise 5 — Set vs List

Two requests both add tag `"vip"` and append alias `"vip"`. Which result can contain duplicates?

**Answer:** The list preserves duplicates; the set does not. List append is non-idempotent under retries after timeouts.

### Exercise 6 — Updating a Field on a Frozen UDT

Schema defines `home frozen<address_info>` and `office address_info`. Why does `SET home.city='Hue'` fail while `SET office.city='Hue'` succeeds?

**Answer:** Frozen UDTs store the whole UDT as one value and forbid partial field mutations; non-frozen UDTs support per-field writes.

### Exercise 7 — `UdtValue` with Omitted Fields

A client constructs a `UdtValue` setting only `city` (omitting `street`/`postal_code`) and writes it to frozen column `home` which previously held full data. Are old fields preserved?

**Answer:** Never assume so. Whole-value replacement on a frozen UDT sets omitted fields to NULL. Merging requires concurrency-controlled read/modify/write or changing the data model.

### Exercise 8 — Decimal with `BigDecimal.equals`

CQL returns `1.00`, expected is `1.0`. `BigDecimal.equals` fails despite equal numeric values. What should you do?

**Answer:** Use `compareTo() == 0` when the contract is numeric equality; if scale is a business invariant, assert scale separately against verified codecs/schemas.

### Exercise 9 — Pre-Epoch Timestamps

An app writes `1969-12-31T23:59:59.123456789Z`. Why might the round-trip lose nanoseconds?

**Answer:** CQL `timestamp` has millisecond precision. Tests should compare against `Instant.ofEpochMilli(input.toEpochMilli())` and avoid hand-rolled epoch math that breaks on negative values.

### Exercise 10 — Single-Node RF1 for QUORUM?

Integration tests using single-node Testcontainers with RF1 pass all reads and writes. Can we conclude an RF3 cluster satisfies `LOCAL_QUORUM` when one DC node is Down?

**Answer:** No. Single-node tests only prove codecs/CQL; availability, repair, and CL must be tested on multi-node topologies with dedicated failure injection.

### Exercise 11 — Invalid UNSET PK

A `BoundStatement` leaves `profile_id` UNSET while binding `note`. The server errors. Should we set `idempotent=true` so the Driver retries?

**Answer:** No. This is a CQL/bind-data validation error; retrying cannot supply a missing PK. Fix input or schema mapping.

### Exercise 12 — Tests Pass Yet the Service Still Misbehaves

Raw Driver UNSET tests pass; Spring repository PATCH still clears the column when the field is absent. Diagnose?

**Answer:** Converters/DTO mapping may coerce absent fields into explicit null or apply a different null-saving policy. Run integration tests through **the real HTTP API → entity/repository → Cassandra path**, not only the low-level driver.

### Lesson Completion Checklist

- [ ] Used real Cassandra via Testcontainers/JUnit for semantics mocks cannot verify.
- [ ] Distinguished ABSENT (API), UNSET (bind), NULL (delete), empty strings/collections.
- [ ] Checked `BoundStatement.isSet()` and reassigned returned instances after `unset`/`setToNull`.
- [ ] Never passed NULL/UNSET for primary keys or invalid WHERE predicates.
- [ ] Checked row existence before getters; checked `isNull` before scalar primitive getters.
- [ ] Handled lists preserving order/duplicates and sets/maps compared by element equality, not iteration order.
- [ ] Never asserted empty and null collections are always distinguishable post-round-trip.
- [ ] Never inserted null elements into collections; wrote layer-accurate negative tests.
- [ ] Accounted for non-idempotent partial collection mutations and list append retries.
- [ ] Built `UdtValue` from session metadata; distinguished frozen vs non-frozen field updates.
- [ ] Tested partial UDTs and isolated schema-evolution scenarios.
- [ ] Tested `tinyint`/`smallint`/`int`/`bigint`/`varint`/`decimal` boundaries and pre-codec overflows.
- [ ] Tested timestamp millisecond precision, pre-epoch dates, leap days, and `LocalTime` nanos.
- [ ] Tested Unicode normalization, `blob` `ByteBuffer`, and DNS-independent IPv4/IPv6.
- [ ] Tested null-saving behavior at the actual Spring Data/Mapper layer when used.
- [ ] Separated codec errors, CQL validation errors, CAS false results, and UNKNOWN timeouts.
- [ ] Enforced test isolation, image/version pinning, CI resource budgets, and a separate multi-node matrix.

## 20. References

1. Apache Cassandra — [CQL Data Types](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html): primitive types, collections, UDTs, null elements, and frozen semantics.
2. Apache Cassandra — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): INSERT/UPDATE/DELETE, conditional statements, TTL, and collection mutations.
3. Apache Cassandra — [Collections](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/collections/collection-create.html): list/set/map, sizing, and query limitations.
4. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): logical deletes, repair, and compaction.
5. Apache Cassandra Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): binding, UNSET, immutable `BoundStatement`.
6. Apache Cassandra Java Driver 4.19 — [Bindable API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Bindable.html): `isSet()` and `unset()`.
7. Apache Cassandra Java Driver 4.19 — [Core Data Types](https://apache.github.io/cassandra-java-driver/4.19.0/core/): scalar/collection Java types, primitive NULLs, and `GenericType`.
8. Apache Cassandra Java Driver 4.19 — [User-Defined Types](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/): `UdtValue`, `UserDefinedType`, and metadata.
9. Apache Cassandra Java Driver 4.19 — [Mapper Null Saving](https://apache.github.io/cassandra-java-driver/4.19.0/mapper/daos/null_saving/): `DO_NOT_SET` and `SET_TO_NULL`.
10. Testcontainers for Java — [Cassandra Module](https://java.testcontainers.org/modules/databases/cassandra/): `CassandraContainer`, `CqlSession`, and TLS configuration.
11. Testcontainers for Java — [JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, lifecycles, and parallel execution limits.
12. Testcontainers — [2.0 Release Notes](https://github.com/testcontainers/testcontainers-java/releases): artifact prefix and container module package changes.
13. Spring Data Cassandra — [Reference](https://docs.spring.io/spring-data/cassandra/reference/): `CassandraTemplate`, entity conversion, and repository integration.
14. JUnit 5 — [User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions, lifecycle, parameterized tests, and reporting.
