# UUIDs and Choosing an ID Generation Strategy by PostgreSQL Version

When designing primary keys for PostgreSQL tables, a common question arises: **should we use auto-incrementing integers or UUIDs, and where should UUIDs be generated?** In systems with multiple services, distributed writes, offline synchronization, or a need to allocate IDs before issuing `INSERT`, UUIDs are a strong candidate.

A frequent point of confusion is that **PostgreSQL has supported the `uuid` data type for a long time, yet built-in UUID generation functions have changed across versions**. An example using `uuidv7()` will run on PostgreSQL 18, but will not run out of the box on PostgreSQL 17. Conversely, older examples requiring `pgcrypto` to call `gen_random_uuid()` are no longer necessary for generating UUIDv4 in PostgreSQL 13 and later.

This lesson explains the nature of UUIDs, how to distinguish important versions, choosing generators matched to your PostgreSQL version, comparing database-side vs. application-side generation, and impacts on primary keys, indexes, queries, and migrations.

## 1. What Is a UUID and Why Does It Need a Dedicated Data Type?

A **UUID (Universally Unique Identifier)** is a 128-bit identifier. A value is commonly displayed as 32 hexadecimal digits divided into groups following the `8-4-4-4-12` pattern:

~~~text
a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
~~~~~~~~-~~~~-~~~~-~~~~-~~~~~~~~~~~~
~~~

The hyphens are purely display formatting for readability; **a UUID value has a logical size of 16 bytes**, not 36 bytes of text in PostgreSQL's `uuid` type.

Example creating a table storing application-supplied UUIDs:

~~~sql
CREATE TABLE example_documents (
    document_id uuid PRIMARY KEY,
    title text NOT NULL
);
~~~

Inserting a valid value:

~~~sql
INSERT INTO example_documents (document_id, title)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
    'Sample document'
);

SELECT
    document_id,
    pg_typeof(document_id) AS id_type,
    pg_column_size(document_id) AS id_bytes
FROM example_documents;
~~~

Expected: `id_type` is `uuid`, and the stored size of the UUID value itself is **16 bytes**. Total row or index size also includes PostgreSQL overhead, so you cannot multiply 16 by row count to get exact total table size.

PostgreSQL accepts several UUID input variants, such as uppercase/lowercase hex digits or omitted hyphens; on output, it normalizes to the standard lowercase hyphenated form.

### Are UUIDs Truly "Guaranteed Globally Unique"?

UUIDs are generated using algorithms with extremely low collision probability or deterministic naming rules. They are **not a mathematical guarantee that every generated value is distinct under all circumstances**. Broken random generators, buggy implementations, or value reuse can still produce duplicates.

Therefore, if a UUID serves as a primary key, you still need:

~~~sql
id uuid PRIMARY KEY
~~~

or an appropriate `UNIQUE` constraint. PostgreSQL will detect and reject duplicate keys.

## 2. Distinguishing the uuid Type from UUID Generation Algorithms

These are independent concepts:

1. **The `uuid` data type:** PostgreSQL stores and compares 128-bit values.
2. **UUID version:** how a value is constructed, such as random v4 or time-ordered v7.
3. **Generator:** the SQL function, extension, or application library that creates a UUID value.

A `uuid` column can hold UUIDv4, UUIDv7, or UUIDs generated outside the database. Declaring a `uuid` column **does not automatically make PostgreSQL generate IDs**; you must supply a `DEFAULT` expression or insert values from the application.

~~~sql
-- Declares the data type, WITHOUT a default:
CREATE TABLE example_ids_manual (
    id uuid PRIMARY KEY
);

-- Also declares a DEFAULT expression generating values
-- using a function available in the active version:
CREATE TABLE example_ids_generated (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid()
);
~~~

These are two independent table definitions. The second runs only where `gen_random_uuid()` is available, such as PostgreSQL 13 and later.

## 3. Common UUID Versions

The UUID version is encoded inside the identifier and specifies the generation algorithm. For PostgreSQL application design, distinguish at least:

| UUID Version | Key Characteristics | Scenarios to Consider |
| --- | --- | --- |
| **v1** | Based on timestamp and node/MAC info per historical algorithm | Legacy interoperability; weigh information-disclosure risks |
| **v3** | Deterministically derived from namespace + name via MD5 | Reproducing identical IDs from identical inputs in legacy systems |
| **v4** | Mostly random bits | General-purpose IDs without time or ordering dependencies |
| **v5** | Deterministically derived from namespace + name via SHA-1 | Mapping an external identifier key into a stable UUID |
| **v7** | Combines Unix timestamp with additional random/counter bits | IDs that tend to sort chronologically, helpful for indexes and event streams |

**UUID version is not PostgreSQL version.** UUIDv7 is a UUID variant, whereas PostgreSQL 18 is a database server version. PostgreSQL 17 can still store valid UUIDv7 values created by an application, even though it **lacks a built-in `uuidv7()` core function**.

### Illustrating Two UUIDs

~~~text
UUIDv4:
a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
              ^
        version nibble = 4

UUIDv7:
019535d9-3df7-79fb-b466-fa907fa17f9e
              ^
        version nibble = 7
~~~

In standard UUID strings, the first hex digit of the third group indicates the version. Avoid parsing UUIDs with manual string slicing in business code when dedicated version-inspection functions or libraries exist.

UUIDv1 can leak creation timestamps and device details from its generator. UUIDv7 embeds timestamp data, so it likewise **should not be treated as hiding creation time**. UUIDv4 generally does not encode generation time in that manner.

## 4. Generator Selection Table by PostgreSQL Version

This is the most important reference when picking a `DEFAULT` function in migrations.

| PostgreSQL | Generating UUIDv4 in SQL | Generating UUIDv7 in SQL | Notes |
| --- | --- | --- | --- |
| **18** | Built-in `gen_random_uuid()` or `uuidv4()` | **Built-in `uuidv7()`** | Can also use `uuid_extract_version()` and `uuid_extract_timestamp()` for v1/v7 |
| **13–17** | **Built-in `gen_random_uuid()`** | No built-in `uuidv7()` | For v7, use an application library or a vetted extension |
| **12 and earlier** | `pgcrypto.gen_random_uuid()` per extension schema, or `uuid_generate_v4()` from `uuid-ossp` | No built-in `uuidv7()` | Requires an extension/library; very old releases need an upgrade plan |

In the bottom row, `pgcrypto.gen_random_uuid()` describes **the `gen_random_uuid` function provided by the pgcrypto extension**; the actual schema where the extension is installed may not be named `pgcrypto`. In SQL, you typically call `gen_random_uuid()` after installing the extension into an appropriate schema on `search_path`.

**Key milestones:**

- **PostgreSQL 13:** `gen_random_uuid()` became a built-in core function for generating UUIDv4.
- **PostgreSQL 18:** added `uuidv7()` for UUIDv7 and `uuidv4()` as an explicit name for UUIDv4.
- `uuid-ossp` remains useful for specialized algorithms like v3/v5 or legacy compatibility.
- You do not need to install `pgcrypto` solely to call built-in `gen_random_uuid()` on PostgreSQL 13–18.

This table describes capabilities in **official PostgreSQL releases**. Managed database services, custom builds, or third-party extensions may differ. When authoring migrations, always verify against the target server rather than assuming from library names in an online snippet.

## 5. Checking Version and Actually Available Functions

Before choosing a `DEFAULT`, connect to the target database and inspect:

~~~sql
SELECT version();

SHOW server_version;

SHOW server_version_num;
~~~

For example, `server_version_num` on PostgreSQL 18 starts around `180000`, while PostgreSQL 17 starts around `170000`. **The server version** determines which core SQL functions are available, not your local `psql` client version.

In modern PostgreSQL, you can check whether a function exists **without calling a nonexistent function**:

~~~sql
SELECT
    to_regprocedure('pg_catalog.gen_random_uuid()')
        AS core_uuid_v4,
    to_regprocedure('pg_catalog.uuidv4()')
        AS core_uuidv4_alias,
    to_regprocedure('pg_catalog.uuidv7()')
        AS core_uuid_v7;
~~~

A `NULL` result means no matching function signature was found in `pg_catalog` on that server. On PostgreSQL 17, the columns for core `uuidv4()` and `uuidv7()` are expected to be `NULL`; PostgreSQL 18 supports all three.

Check extensions installed in the **current database**:

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
WHERE extname IN ('pgcrypto', 'uuid-ossp')
ORDER BY extname;
~~~

And extensions available for installation on the server:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
WHERE name IN ('pgcrypto', 'uuid-ossp');
~~~

Absence of an extension in `pg_extension` does not mean core UUIDv4 support is absent. Conversely, seeing an extension in `pg_available_extensions` does not prove it is **installed in your database** or that your role has permission to install it.

## 6. PostgreSQL 13–17: Using gen_random_uuid() for UUIDv4

On PostgreSQL 13 and later, `gen_random_uuid()` is the simplest approach for database-generated UUIDv4 primary keys.

~~~sql
CREATE TABLE customers_v4 (
    customer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Insert data and let the server generate the ID:

~~~sql
INSERT INTO customers_v4 (email, full_name)
VALUES ('an@example.test', 'An')
RETURNING customer_id, email;
~~~

The output contains a freshly generated UUIDv4. The exact value **changes on every run**; never hardcode an "expected" UUID for a random generator.

### Why Use DEFAULT?

When a column has `DEFAULT gen_random_uuid()`, an `INSERT` **omitting the ID column** invokes the generator to populate it:

~~~sql
INSERT INTO customers_v4 (email, full_name)
VALUES ('binh@example.test', 'Binh');
~~~

You can also request `DEFAULT` explicitly:

~~~sql
INSERT INTO customers_v4 (customer_id, email, full_name)
VALUES (
    DEFAULT,
    'chi@example.test',
    'Chi'
);
~~~

If the application supplies a specific UUID, the database uses that exact value instead of calling the default:

~~~sql
INSERT INTO customers_v4
    (customer_id, email, full_name)
VALUES (
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid,
    'dung@example.test',
    'Dung'
);
~~~

If you explicitly pass SQL `NULL` for the primary key, `DEFAULT` **does not replace NULL automatically**; `PRIMARY KEY` still rejects NULL. This differs from **omitting the column from the INSERT**.

### When to Choose v4?

UUIDv4 is well-suited when:

- Multiple applications or databases must generate IDs without requesting numbers from a central sequence.
- IDs do not need to reflect creation time.
- You want to avoid exposing record counts via sequential integer IDs.
- Data volume and write throughput have not made random-ID index locality a bottleneck.

UUIDv4 **is not a secret token**. Even though it is harder to guess than sequential integers, the server must still enforce user/tenant authorization on reads and writes.

## 7. PostgreSQL 18: Using uuidv7() for Approximately Time-Ordered Identifiers

PostgreSQL 18 adds the core function:

~~~sql
SELECT uuidv7();
~~~

It generates **UUIDv7** with a timestamp prefix and additional data so values tend to sort chronologically. You can use it as a default:

~~~sql
CREATE TABLE events_v7 (
    event_id uuid PRIMARY KEY DEFAULT uuidv7(),
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Inserting events:

~~~sql
INSERT INTO events_v7 (event_type, payload)
VALUES
    ('order_created', '{"order_id":1001}'::jsonb),
    ('order_paid',    '{"order_id":1001}'::jsonb)
RETURNING event_id, event_type, created_at;
~~~

`event_id` is generated by PostgreSQL 18. `created_at` is still stored separately even though the ID embeds a timestamp, because UUIDv7's timestamp **does not replace full business temporal semantics**.

### Why Does v7 Often Benefit B-Tree Indexes?

A UUIDv4 primary key distributes values randomly across the key space, so new `INSERT`s can touch arbitrary regions of the B-tree index.

UUIDv7 places time information at the leading edge of the identifier, so IDs generated close together in time **tend to cluster near each other in index order**. In continuous-write workloads, this can reduce random insertion scatter, page splits, or cache misses compared to UUIDv4.

However, there is no guarantee that `uuidv7()` is always faster:

- UUIDv7 is still a 128-bit UUID; it is not as compact as a 64-bit `bigint`.
- Multiple concurrent generators, clock skew, or differing generator implementations can cause ID order to diverge slightly from commit order.
- Actual performance depends on indexes, table size, fillfactor, concurrency, WAL, autovacuum, read/write mix, and server configuration.
- On small tables, the difference may be negligible.

**Measure on realistic workloads** before converting every primary key to v7 solely because it is labeled "time-ordered".

### Additional Functions in PostgreSQL 18

~~~sql
SELECT
    uuidv4() AS random_uuid,
    uuidv7() AS time_ordered_uuid;
~~~

`uuidv4()` is an explicit name for UUIDv4; `gen_random_uuid()` remains usable.

The `uuidv7()` function also accepts an optional `shift interval` parameter to shift its timestamp portion within permitted bounds. Most applications **do not need shift**; avoid arbitrarily shifting timestamps and distorting temporal meaning.

To inspect version and timestamp:

~~~sql
SELECT
    event_id,
    uuid_extract_version(event_id) AS uuid_version,
    uuid_extract_timestamp(event_id) AS embedded_time
FROM events_v7
ORDER BY event_id;
~~~

For UUIDv7 values, `uuid_extract_version` returns `7` and `uuid_extract_timestamp` extracts the encoded timestamp from the ID.

**Version note:** PostgreSQL 17 already had functions to extract version and timestamp for **UUIDv1**; PostgreSQL 18 extended timestamp extraction to **UUIDv7**. On PostgreSQL 17, do not expect `uuid_extract_timestamp` to extract timestamps from UUIDv7 as it does on 18.

### Can ORDER BY uuid Replace ORDER BY created_at?

You can sort with `ORDER BY event_id` and with UUIDv7 get an order reflecting the ID's encoded timestamp. Yet that **is not an absolute guarantee of commit order or business time**:

- `now()` in PostgreSQL captures transaction start time; multiple rows inserted in one transaction can share the exact same `created_at`.
- An ID may be generated before the transaction commits.
- Different processes or machines can have clock skew.
- UUIDv7 values can be imported from external systems or pre-generated.
- Event receipt/commit order and ID generation order do not always match.

If the business requires "the latest event", define ordering using `created_at` or a dedicated sequence/event-position column with deterministic tie-breakers. UUIDv7 provides helpful ID ordering properties, **not cryptographic or transactional proof of commit timing**.

## 8. PostgreSQL 12 and Earlier: pgcrypto for UUIDv4

In older releases before `gen_random_uuid()` became a core function, a common way to generate UUIDv4 was the `pgcrypto` extension.

Install the extension in the **connected database**, when available on the server and permitted for your role:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

Then:

~~~sql
SELECT gen_random_uuid();
~~~

And in a schema:

~~~sql
CREATE TABLE legacy_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name text NOT NULL
);
~~~

**Never run `CREATE EXTENSION` on production just to follow a tutorial** without checking operational policy. Extensions must exist in the server build, require privileges to install, and may be restricted in managed PostgreSQL services.

### What About pgcrypto in Newer Versions?

In newer PostgreSQL versions, `pgcrypto` still provides many cryptographic utilities. However, its `gen_random_uuid()` effectively acts as compatibility alongside the built-in core function. Therefore:

- If you **only need UUIDv4 on PostgreSQL ≥ 13**, prefer the built-in `gen_random_uuid()`.
- If you need `pgcrypto`'s specific cryptographic functions, the extension still serves its own role.
- On PostgreSQL 12 and earlier, `pgcrypto` works if supported by your environment, while you should plan a major upgrade since older versions have reached end-of-life.

How you generate UUIDv4 **does not change the column type**: `event_id` remains `uuid`. Only the function supplying the value changes.

## 9. uuid-ossp: When You Need v1, v3, v4, or v5

The `uuid-ossp` extension provides classic standard UUID algorithms used by many legacy systems, including:

| Function | Meaning |
| --- | --- |
| `uuid_generate_v1()` | UUIDv1, based on timestamp and node info |
| `uuid_generate_v1mc()` | v1 variant using a random multicast MAC instead of the real MAC |
| `uuid_generate_v3(namespace, name)` | Deterministic UUIDv3 from namespace and name |
| `uuid_generate_v4()` | Random UUIDv4 |
| `uuid_generate_v5(namespace, name)` | Deterministic UUIDv5 from namespace and name |

Install when justified and authorized:

~~~sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
~~~

Because the extension name contains a hyphen, it must be **double-quoted** in SQL.

UUIDv4 example via the extension:

~~~sql
SELECT uuid_generate_v4();
~~~

On PostgreSQL 13+, installing `uuid-ossp` solely for v4 is unnecessary. However, `uuid-ossp` is valuable if you need older UUID versions or **name-based deterministic IDs**.

### UUIDv5: Same Namespace and Name Yield the Same ID

~~~sql
SELECT
    uuid_generate_v5(
        uuid_ns_url(),
        'https://example.test/catalog/sku-501'
    ) AS product_uuid;
~~~

Running this again with the **exact same namespace and name string** yields the **exact same UUIDv5**. Changing either name or namespace produces a different ID.

This helps when mapping a stable external identity into a UUID without maintaining a separate lookup table—for instance, from a canonicalized resource code.

Proceed with caution:

- Input names must follow strict canonicalization rules, especially casing, Unicode normalization, and path formatting.
- UUIDv5 **is not a secure cryptographic signature** and must not be used to hide secret input data.
- The same name under two namespaces produces two different UUIDs.
- If a business code can change, deriving v5 directly from it causes the same entity to receive a different ID.
- Different libraries must encode input strings identically to ensure compatible results.

### Should UUIDv1 Be Used for New Primary Keys?

UUIDv1 has time ordering, yet can expose timestamp and node/MAC details depending on the generator. For new systems, usually evaluate **v4** for random IDs or **v7** for time-ordered IDs before choosing v1, unless explicit legacy compatibility demands it.

Traditional `uuid-ossp` **is not the core `uuidv7()` function**. Do not assume installing `uuid-ossp` provides `uuid_generate_v7()` across all versions.

## 10. Want UUIDv7 Before Upgrading the Database to PostgreSQL 18?

PostgreSQL 13–17 still provides the `uuid` type and can **store UUIDv7** generated externally. Practical options include:

1. **Generate in the application** using a vetted RFC 9562-compliant UUIDv7 library.
2. **Install a third-party PostgreSQL extension** providing UUIDv7 if approved by DBAs, supported by your server/managed host, and vetted for security and reliability.
3. **Upgrade the server to PostgreSQL 18** via a proper upgrade/migration workflow to use core `uuidv7()`.

Example of an application generating UUIDv7 and passing it via JDBC:

~~~java
// idV7 is generated by a trusted UUIDv7 library.
// This is a java.util.UUID object, not a hand-built SQL string.
UUID idV7 = uuidV7Generator.generate();

String sql = """
    INSERT INTO events (event_id, event_name)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, idV7);
    ps.setString(2, "OrderCreated");
    ps.executeUpdate();
}
~~~

This illustrates binding a UUID; `uuidV7Generator` is an application-provided abstraction, not a built-in standard Java method. It assumes `events(event_id uuid, event_name text)` exists and the JDBC driver supports `java.util.UUID` mapping like standard pgJDBC.

**Never hand-roll v7 by simply concatenating a timestamp with random hex** without fully verifying version/variant bits, validity, entropy, and concurrency safety. Generator bugs can cause collisions or non-compliant UUIDs.

## 11. Generate IDs in the Database or in the Application?

This architectural decision is independent of choosing UUIDv4 vs. UUIDv7.

| Criterion | Database-Generated | Application-Generated |
| --- | --- | --- |
| Example | `DEFAULT gen_random_uuid()` or `DEFAULT uuidv7()` | Java UUID/library creates ID before `INSERT` |
| Advantage | Centralized generation, all clients share one default | ID is known prior to DB write, convenient for distributed flows |
| Dependency | PostgreSQL server version/function/extension | Library version and configuration across all clients |
| Passing ID | Can use `INSERT ... RETURNING id` | Pass via parameter; immediately available for messages/tracing |
| Algorithm consistency | Follows configured database server | Must ensure every service uses the right generator |
| Time inside ID | DB server clock if v7 generated in DB | App node clock if v7 generated in app |
| Risks | Version mismatch across DB environments | Buggy library, clock skew, inconsistent configs |

### Database Generates, Application Reads Back the ID

~~~sql
INSERT INTO customers_v4 (email, full_name)
VALUES ('em@example.test', 'Em')
RETURNING customer_id;
~~~

`RETURNING` retrieves the server-generated value without requiring a follow-up query by email.

### Application Generates, Then Inserts

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public static UUID createCustomer(
    Connection connection, String email, String name
) throws SQLException {
    UUID newId = UUID.randomUUID(); // UUIDv4 in Java

    String sql = """
        INSERT INTO customers_v4 (customer_id, email, full_name)
        VALUES (?, ?, ?)
        """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setObject(1, newId);
        ps.setString(2, email);
        ps.setString(3, name);
        ps.executeUpdate();
    }
    return newId;
}
~~~

This Java example uses `java.util.UUID.randomUUID()`, which generates **v4**, not v7. If the system needs application-side v7, replace it with an appropriate v7 generator.

### Pitfalls to Avoid When Generating in the Application

- Never construct UUIDs using `Math.random()` or weak PRNGs that violate algorithmic requirements.
- Never interpolate UUIDs into SQL strings; bind parameters.
- Never unconditionally generate a new UUID on every retry if the ID must act as a stable idempotency key. When retrying a submitted operation, you often need to **reuse the same request ID** per business design.
- Never treat `UUID.randomUUID()` as an authentication mechanism or secret security token.

When multiple services generate IDs, align on policy, monitor collisions, and keep `PRIMARY KEY`/`UNIQUE` in the database as the final safeguard.

## 12. UUID vs. bigint GENERATED AS IDENTITY: Which to Choose?

PostgreSQL provides numeric key generation via identity columns:

~~~sql
CREATE TABLE customers_identity (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE
);
~~~

Comparison:

| Property | `bigint identity` | UUIDv4 | UUIDv7 |
| --- | --- | --- | --- |
| Value size | 8 bytes | 16 bytes | 16 bytes |
| Typical generation | Database sequence | Random in DB or app | Time-ordered in DB 18+ or app |
| Can be generated offline independently | Not by default | Yes | Yes |
| Does ID order carry time meaning? | Roughly allocation order, not commit guarantee | No | Follows timestamp tendency, not commit guarantee |
| B-tree insertion pattern | Mostly near the end of the index | Randomly scattered | Generally time-localized |
| Guessability of next ID | Easily predictable sequentially | Harder to predict | May reveal timing info |
| Simplicity | Very simple in single-DB systems | Broadly supported everywhere | Requires checking version/generator |

There is no universal "winner" for every system.

- If an application writes solely to one PostgreSQL database and needs simple internal IDs, `bigint identity` can be compact and easy to manage.
- If IDs must be allocated across multiple services/nodes before writing, UUIDs are more convenient.
- If you need UUIDs while improving locality on heavy write tables, consider UUIDv7 when a trustworthy generator is available.
- If you already have stable `bigint` primary keys performing well, do not rewrite them merely because UUIDs are trendy.

**Do not substitute UUIDs for authorization.** Both numeric keys and UUIDs are just identifiers; APIs must still verify ownership and tenant access.

## 13. Store UUIDs as the uuid Type, Not Arbitrary text

Suppose the same ID is stored in two column types:

~~~sql
CREATE TABLE bad_identifiers (
    id_text text PRIMARY KEY
);

CREATE TABLE good_identifiers (
    id uuid PRIMARY KEY
);
~~~

With `text`, the database does not validate UUID syntax by default. Invalid strings like `'abc'`, inconsistent casing, or varied hyphen formatting for the same identifier can slip in.

With `uuid`:

- Values are validated and normalized as UUIDs at parse time.
- Stored in 128-bit binary form rather than character strings with extra overhead.
- Provides native operators and an appropriate B-tree operator class.
- Clients/JDBC can pass `java.util.UUID` directly.
- Foreign keys share clean, exact type safety.

Example:

~~~sql
SELECT
    'A0EEBC99-9C0B-4EF8-BB6D-6BB9BD380A11'::uuid
        AS canonical_uuid;
~~~

Output displays in standard lowercase UUID format.

### Querying UUIDs with the Proper Type

~~~sql
SELECT customer_id, email
FROM customers_v4
WHERE customer_id =
      'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid;
~~~

When passing from an application, prefer binding a typed UUID:

~~~java
UUID id = UUID.fromString(inputId);

String sql =
    "SELECT email FROM customers_v4 WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("email"));
        }
    }
}
~~~

`UUID.fromString` can throw `IllegalArgumentException` on malformed strings; translate that into an input validation error at the API layer rather than an unhandled 500 server error. This snippet assumes standard JDBC imports and a valid `connection` variable.

**Do not cast the column to text to compare without good reason**, such as:

~~~sql
-- Not a standard choice for UUID primary key lookups:
WHERE customer_id::text = '...'
~~~

Casting the column can prevent a normal B-tree index on `customer_id` from being used efficiently for UUID equality lookups. Keep comparisons in the `uuid` type and bind typed parameters.

## 14. UUIDs as Foreign Keys and Composite Keys

UUIDs work cleanly as foreign keys.

~~~sql
CREATE TABLE customer_addresses_v4 (
    address_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id uuid NOT NULL
        REFERENCES customers_v4(customer_id)
        ON DELETE CASCADE,
    address_text text NOT NULL
);

CREATE INDEX idx_addresses_customer_id
ON customer_addresses_v4(customer_id);
~~~

When adding an address, supply an existing customer ID:

~~~sql
INSERT INTO customer_addresses_v4 (customer_id, address_text)
SELECT customer_id, '12 Example Street'
FROM customers_v4
WHERE email = 'an@example.test';
~~~

Foreign keys on UUIDs obey the exact same rules as numeric foreign keys: PostgreSQL checks parent existence, enforces `ON DELETE` behavior, and protects referential integrity.

**Index note:** `PRIMARY KEY` creates an index on the parent key; PostgreSQL **does not automatically create indexes on child foreign-key columns**. For queries filtering by `customer_id` or when deleting/updating parent rows, an index on the child side is usually helpful.

If a join table has two UUID foreign keys:

~~~sql
CREATE TABLE memberships_v4 (
    customer_id uuid NOT NULL
        REFERENCES customers_v4(customer_id),
    group_id uuid NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, group_id)
);
~~~

the composite primary key guarantees each pair is unique. If `group_id` must reference an actual groups table, create that table and add the foreign key; merely declaring `uuid` creates no relationship.

## 15. How Do UUIDv4 and UUIDv7 Affect Indexes?

PostgreSQL primary keys default to B-tree indexes; UUIDs use B-tree indexes as well.

### UUIDv4: Random Values

Under continuous `INSERT`s with UUIDv4, new keys land across scattered locations in the B-tree. On large tables with high write rates, this can increase page writes, page splits, and cache churn.

### UUIDv7: Approximately Time-Ordered

With UUIDv7, the leading bits carry timestamp data, so new keys tend to cluster toward the right/tail edge of the index. This is a potential advantage for insert-heavy workloads.

~~~mermaid
flowchart LR
    A["Continuous INSERT stream"] --> B{"ID Strategy"}
    B -->|"UUIDv4"| C["Keys scattered across UUID space"]
    B -->|"UUIDv7"| D["Keys tend to increase with timestamp"]
    C --> E["May touch many B-tree regions"]
    D --> F["May improve write locality"]
    E --> G["Measure on real workload"]
    F --> G
~~~

Still, this is a **directional tendency**, not a measurement. Never treat a diagram as 100% proof that v7 always beats v4 or shrinks down to `bigint`.

Metrics to benchmark:

1. `INSERT` throughput and transaction latency.
2. B-tree index size and bloat/fragmentation.
3. WAL generation, cache hit rate, I/O, and page splits under representative load.
4. `UPDATE`/`DELETE` performance and number of related foreign keys.
5. Concurrency, data distribution, and read/write ratio.
6. Multi-service ID generation, clock skew, and historical backfill behavior.

Benchmark in a realistic test environment; do not extrapolate from a tiny table of dozens of rows to hundreds of millions of rows.

## 16. UUIDv7 Does Not Replace Business Timestamp Columns

Because v7 embeds a timestamp, you might be tempted to drop `created_at`. That is a mistake.

Comparison:

| Aspect | UUIDv7 | `created_at timestamptz` |
| --- | --- | --- |
| Contains time info | Yes, inside ID | Yes, explicitly |
| Default semantics | Moment the generator created the UUID | As defined by application/DB rules |
| Convenient for SQL time ranges | Requires UUID extraction/comparison mechanics | Direct timestamp predicates |
| Represents exact commit time | No | Not automatically either, if populated via `now()` before commit |
| Supports time-range indexing | Relative ordering via UUIDv7 | B-tree/BRIN on timestamp when appropriate |
| Suitable as sole audit proof | No | Still requires proper audit design and trusted clock sources |

Example querying events by business time:

~~~sql
SELECT event_id, event_type, created_at
FROM events_v7
WHERE created_at >= timestamptz '2026-11-01 00:00:00+00'
  AND created_at <  timestamptz '2026-12-01 00:00:00+00'
ORDER BY created_at, event_id;
~~~

Using a **half-open** interval avoids end-of-day precision assumptions. For such queries, consider indexing `created_at` according to your workload.

`uuid_extract_timestamp` in PostgreSQL 18 is handy for technical diagnostics and validating UUIDv7s, yet the timestamp embedded inside an ID is not necessarily the authoritative business timestamp.

## 17. Two-Branch Practice Workflow by Version

To avoid "function does not exist" errors, **pick the branch matching your server** instead of executing every statement in one script.

### Branch A: PostgreSQL 13–18, UUIDv4

In a separate lab database:

~~~sql
CREATE SCHEMA IF NOT EXISTS uuid_lab;

CREATE TABLE uuid_lab.notes_v4 (
    note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    note_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO uuid_lab.notes_v4 (note_text)
VALUES
    ('First note'),
    ('Second note')
RETURNING note_id, note_text;

SELECT
    note_id,
    note_text,
    pg_column_size(note_id) AS uuid_bytes
FROM uuid_lab.notes_v4
ORDER BY created_at, note_id;
~~~

Expected result: two rows, each `note_id` of type `uuid` with a 16-byte value size. Generated IDs will differ on every run.

If the table already exists from a prior lab run, do not re-run `CREATE TABLE` without handling existing state. In shared labs, use separate schemas/databases per run or drop tables **only when certain they contain solely your practice data**.

### Branch B: PostgreSQL 18 Only, UUIDv7

~~~sql
CREATE SCHEMA IF NOT EXISTS uuid_lab;

CREATE TABLE uuid_lab.notes_v7 (
    note_id uuid PRIMARY KEY DEFAULT uuidv7(),
    note_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO uuid_lab.notes_v7 (note_text)
VALUES
    ('Event A'),
    ('Event B')
RETURNING
    note_id,
    uuid_extract_version(note_id) AS version,
    uuid_extract_timestamp(note_id) AS timestamp_in_uuid;

SELECT note_id, note_text
FROM uuid_lab.notes_v7
ORDER BY note_id;
~~~

The new `note_id` values are generated as UUIDv7. `uuid_extract_version` returns `7` for values created by `uuidv7()`. IDs tend to sort chronologically, though for two rows inserted close together you must not assert that every embedded timestamp differs or that ID order equals exact commit order.

### Branch C: PostgreSQL 12 and Earlier, UUIDv4 via Extension

~~~sql
-- Run only if the server provides pgcrypto and your role has install privileges.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS uuid_lab;

CREATE TABLE uuid_lab.notes_legacy (
    note_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    note_text text NOT NULL
);

INSERT INTO uuid_lab.notes_legacy (note_text)
VALUES ('Legacy version note')
RETURNING note_id;
~~~

If `pgcrypto` cannot be installed, check server/managed-service policies; never bypass permissions or copy unvetted functions manually. Consider `uuid-ossp` or application-side generation instead.

### Validating Whether a Specific UUID String Is Valid

~~~sql
SELECT
    'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid AS valid_uuid;
~~~

An invalid UUID string raises a cast error:

~~~sql
-- Intentionally failing example; run separately when practicing error handling.
SELECT 'not-a-uuid'::uuid;
~~~

Never rely on failing casts inside a production data migration script. When source data has not been sanitized, validate and clean malformed records before altering column types.

## 18. Migrating an Existing bigint Table to UUID: A Migration Plan Is Required

You cannot simply run:

~~~sql
-- Not a valid semantic default conversion:
ALTER TABLE orders
ALTER COLUMN id TYPE uuid;
~~~

A `bigint` value has no automatic standard mapping to a UUID. If child tables reference `orders.id`, changing the primary key impacts all foreign keys, applications, indexes, caches, APIs, and linked data.

A conceptual migration plan:

1. **Clarify the goal:** do you need distributed IDs, reduced ID guessability, or better index locality?
2. **Select a UUID version and generator** compatible with all servers and writing clients.
3. **Add a new UUID column** with controlled backfilling; account for large tables and avoid long locks.
4. **Populate UUIDs for all existing rows** and ensure uniqueness; never regenerate IDs arbitrarily if the migration re-runs.
5. **Add UUID columns in child tables**, populate via an `old_id → new_uuid` mapping, and verify zero orphan references.
6. **Create indexes and constraints in the right order**, using online/concurrent index creation where supported.
7. **Transition applications via controlled dual-read/dual-write** or a carefully staged rollout.
8. **Verify data, foreign keys, and rollback strategy** before switching the primary key officially.
9. **Drop the old ID only** after all consumers have migrated and recovery plans are in place.

Some migrations keep `bigint` as the **internal primary key** and add a `public_id uuid UNIQUE` for external APIs:

~~~sql
CREATE TABLE example_orders_public_id (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    order_status text NOT NULL
);
~~~

This keeps internal foreign keys compact and stable while external consumers use UUIDs. The trade-off is maintaining both columns, an extra index, and code-level mapping.

Do not replace a production primary key merely to make URLs look random. Authorization remains mandatory, and adding an external identifier is often far less risky than replacing every relational key.

## 19. Validating UUIDs and Handling Errors at the Application Layer

### Malformed UUID Values

When casting from `text`/`varchar` to `uuid`, PostgreSQL validates syntax. For example:

~~~sql
SELECT 'not-a-uuid'::uuid;
~~~

A cast error is not "record not found"; it is an invalid input error. APIs should return an appropriate validation error (e.g., 400) instead of letting an unhandled SQL exception become a 500 server error.

### Duplicate IDs

Even with a highly reliable generator, the database still needs a primary key. When an `INSERT` hits an existing UUID, PostgreSQL raises a unique violation (SQLSTATE `23505`). The application must distinguish **retries of the same operation** from **true collisions or anomalous data**.

Do not resolve every unique error by blindly generating a new ID and retrying forever. For idempotent operations or workflows that already emitted events with the original ID, changing the ID can break links and create duplicate records.

### API Security

An unpredictable-looking UUID does not mean open access:

~~~sql
SELECT order_status
FROM example_orders_public_id
WHERE public_id = $1;
~~~

This query does not check whether the caller is authorized to view the order. Combine it with owner/tenant/authorization predicates from the authenticated context per system design.

UUIDv7 embeds timestamps, and UUIDv1 can expose node info and timestamps; never use these UUIDs as secret credentials or authentication tokens.

## 20. Common Mistakes When Choosing a Generator

### Mistake 1: Assuming Having the uuid Type Means All UUID Functions Exist

The data type is widely supported, yet core `uuidv7()` only arrived in PostgreSQL 18. Check `server_version` or function presence before writing migrations.

### Mistake 2: Assuming PostgreSQL 17 Needs pgcrypto for gen_random_uuid()

Not needed. Since PostgreSQL 13, `gen_random_uuid()` has been a built-in core function for UUIDv4. `pgcrypto` remains useful for other cryptography, not strictly for creating UUIDv4.

### Mistake 3: Assuming Installing uuid-ossp Provides uuidv7()

`uuid-ossp` provides traditional algorithms such as v1, v3, v4, and v5. Do not assume `uuid_generate_v7()` exists on PostgreSQL 17 simply because the extension is installed.

### Mistake 4: Generating UUIDv4 and Expecting ORDER BY id to Reflect Creation Order

UUIDv4 is random; `ORDER BY id` does not reflect insertion order. If creation order is needed, use `created_at` or a proper ordering column.

### Mistake 5: Using UUIDv7 and Dropping created_at

UUIDv7 carries the generator's approximate timestamp, not a substitute for business time, commit time, auditing, or multi-source ordering rules.

### Mistake 6: Assuming UUIDv7 Is Guaranteed Faster Than bigint and UUIDv4

UUIDv7 offers potential locality advantages, yet remains 16 bytes with index overhead and workload-dependent behavior. Benchmark real data.

### Mistake 7: Storing UUIDs in varchar(36) Because They Look Like Strings

Use `uuid` so PostgreSQL validates, normalizes, and stores them efficiently. Use text only when a specific compatibility constraint requires it.

### Mistake 8: Using a UUID as a Secret Access Token

IDs identify resources; they do not replace authorization checks. Never equate hard-to-guess IDs with access security.

### Mistake 9: Generating a Fresh UUID on Every Retry Regardless of State

If a request succeeded on the server before the client lost connection, retrying with a new ID can create a second record. Design business-level idempotency rather than relying solely on UUID uniqueness.

### Mistake 10: Ignoring Multi-Version Database Rollouts

An app targeting PostgreSQL 18 using `uuidv7()` as a default will fail on lower-version replicas, staging servers, or migrations. Identify the lowest server version **executing the DDL/expression** and coordinate upgrade paths.

### Mistake 11: Extracting Timestamps from UUIDs on Any PostgreSQL Version

`uuid_extract_timestamp()` support varies by version. PostgreSQL 18 supports UUIDv1/v7, whereas earlier releases do not automatically support v7.

### Mistake 12: Omitting PRIMARY KEY Assuming Collisions Never Happen

Low collision probability does not replace constraints. For critical data, the database must enforce uniqueness.

## 21. Practice Exercises

### Exercise 1: Choosing a Generator for PostgreSQL 16

An `api_requests` table needs a UUID primary key on PostgreSQL 16 without installing extensions. Write the DDL.

**Answer:**

~~~sql
CREATE TABLE api_requests (
    request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_path text NOT NULL
);
~~~

This generates UUIDv4 using the built-in core function.

### Exercise 2: Choosing a Generator for PostgreSQL 18

A high-write events table needs IDs that tend to sort chronologically. Write the DDL and insert a row.

**Answer:**

~~~sql
CREATE TABLE audit_events (
    event_id uuid PRIMARY KEY DEFAULT uuidv7(),
    event_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO audit_events (event_type)
VALUES ('document_updated')
RETURNING event_id, created_at;
~~~

`uuidv7()` requires PostgreSQL 18 or later. `created_at` preserves separate business temporal semantics.

### Exercise 3: PostgreSQL 12 Reports "function gen_random_uuid does not exist"

Explain why and provide a valid resolution.

**Answer:** In PostgreSQL 12, `gen_random_uuid()` is not a built-in core function. You can install `pgcrypto` (if available, permitted, and operationally approved) or use another generator like `uuid-ossp` or an application library. Also plan a major version upgrade since PostgreSQL 12 is end-of-life.

### Exercise 4: Does Generating the Same UUIDv5 Twice Collide?

~~~sql
SELECT uuid_generate_v5(
    uuid_ns_url(),
    'https://example.test/items/42'
);
~~~

With the same extension, namespace, and name string, the generated UUID is **identical** every time. If every insert must produce a distinct ID, name-based deterministic UUIDv5 is not the right choice.

### Exercise 5: Why Is UUIDv4 Unsuitable for Ordering Records?

~~~sql
SELECT customer_id
FROM customers_v4
ORDER BY customer_id;
~~~

Exercise: re-run after inserting several rows. Output sorts by **UUID value**, not creation time, because v4 is random.

### Exercise 6: Distinguishing uuid and varchar

Compare `orders(id uuid)` and `orders_text(id varchar(36))`. Which validates UUID input format automatically? Which stores a 16-byte logical value with dedicated operators and indexes?

**Answer:** `uuid`. `varchar(36)` only caps string length and can hold non-UUID strings without extra validation.

### Exercise 7: Application-Side UUIDv7 in Java with PostgreSQL 17

The application has a standard UUIDv7 library and PostgreSQL 17 only needs to store the IDs. Design the insert pattern.

**Answer:** The column uses type `uuid`; the application generates UUIDv7 via the library and binds it using `PreparedStatement.setObject(index, javaUuid)`. Do not call `uuidv7()` in SQL on PostgreSQL 17 unless a vetted extension provides that function.

### Exercise 8: Protecting Foreign Keys

`customers_v4` has `customer_id uuid PRIMARY KEY`. An `orders_v4` table has `customer_id uuid`. What constraint is needed to prevent referencing nonexistent customers and disallow orders without a customer?

**Answer:**

~~~sql
customer_id uuid NOT NULL
    REFERENCES customers_v4(customer_id)
~~~

Also consider an index on `orders_v4(customer_id)` based on workload, since PostgreSQL does not auto-index child FK columns.

### Exercise 9: Should Legacy bigint Keys Be Replaced with UUID Everywhere?

A system has hundreds of child tables using `bigint` foreign keys, yet needs unpredictable public IDs. Propose a lower-impact option.

**Hint:** Keep `bigint` as the internal key, add `public_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid()` on tables requiring public IDs, and migrate APIs to use `public_id`. Full authorization checks are still required.

## 22. Decision Flow for Choosing a UUID by Version and Requirements

~~~mermaid
flowchart TD
    A["Need a new ID"] --> B{"Must it be a UUID?"}
    B -->|"No"| C["Consider bigint IDENTITY and business keys"]
    B -->|"Yes"| D{"Want time-ordered UUIDs?"}
    D -->|"No"| E{"PostgreSQL >= 13?"}
    E -->|"Yes"| F["gen_random_uuid() - core UUIDv4"]
    E -->|"No"| G["pgcrypto / uuid-ossp / application"]
    D -->|"Yes"| H{"PostgreSQL >= 18?"}
    H -->|"Yes"| I["core uuidv7()"]
    H -->|"No"| J["Vetted app/extension v7 generator"]
    F --> K["Choose DB DEFAULT vs app generator"]
    G --> K
    I --> K
    J --> K
    K --> L["PRIMARY KEY/UNIQUE, indexes, and access control"]
~~~

You can turn this diagram into design questions:

1. **Local or distributed IDs?** If IDs are only needed inside one database, `bigint identity` may suffice.
2. **Which version?** v4 is simple and universal; v7 tends toward time ordering; v5 is for name-based deterministic IDs.
3. **Which server version?** 13–17 provide `gen_random_uuid()`; PostgreSQL 18 adds `uuidv7()` and `uuidv4()`.
4. **Who generates IDs?** Database `DEFAULT` or application; stay consistent across services.
5. **Which storage type?** Use `uuid`, not text by default.
6. **What query and index requirements exist?** Review foreign keys, B-tree locality, `created_at`, pagination, and write load.
7. **What security requirements exist?** UUIDs do not replace authorization, idempotency, or auditing.
8. **What compatibility/upgrade constraints exist?** Check staging, replicas, disaster recovery, and the minimum PostgreSQL version that migrations must support.

## 23. Official Documentation References

To verify exact behavior when upgrading or operating a specific major version:

- [PostgreSQL 18 — UUID Type](https://www.postgresql.org/docs/18/datatype-uuid.html): data type, storage format, and UUID semantics.
- [PostgreSQL 18 — UUID Functions](https://www.postgresql.org/docs/18/functions-uuid.html): `gen_random_uuid()`, `uuidv4()`, `uuidv7()`, and version/timestamp extraction functions.
- [PostgreSQL 17 — UUID Functions](https://www.postgresql.org/docs/17/functions-uuid.html): core functions prior to `uuidv7()`.
- [PostgreSQL 13 — UUID Functions](https://www.postgresql.org/docs/13/functions-uuid.html): milestone introducing `gen_random_uuid()` into core.
- [PostgreSQL 12 — pgcrypto](https://www.postgresql.org/docs/12/pgcrypto.html): UUIDv4 generation in older versions.
- [PostgreSQL 18 — uuid-ossp](https://www.postgresql.org/docs/18/uuid-ossp.html): additional UUIDv1/v3/v4/v5 functions.
- [PostgreSQL — Versioning Policy](https://www.postgresql.org/support/versioning/): check which major versions remain supported.

## 24. Summary

**Having the `uuid` type does not imply a single fixed UUID generator across all PostgreSQL versions.** To write accurate migrations and applications, distinguish the **PostgreSQL** version from the **UUID** version:

- **PostgreSQL 13–17:** use core `gen_random_uuid()` for UUIDv4; `pgcrypto` is not required just for this.
- **PostgreSQL 18:** adds `uuidv7()` for time-ordered UUIDv7 and `uuidv4()` as an explicit name for v4.
- **PostgreSQL 12 and earlier:** can generate UUIDv4 via `pgcrypto` or `uuid-ossp` when permitted and supported.
- **Any version supporting `uuid`:** can store application-generated UUIDs, including UUID versions lacking a server core generator.

Choose v4 for simple random identifiers; consider v7 when time-ordered UUIDs and index locality matter; use v5 for deterministic namespace–name mappings. Whichever option you choose, retain uniqueness constraints, foreign keys, access controls, and independent business timestamps where required.

A solid identifier is not just properly formatted: it is compatible with your running server version, reliably generated, and aligned with your queries, indexes, migrations, and operational needs.
