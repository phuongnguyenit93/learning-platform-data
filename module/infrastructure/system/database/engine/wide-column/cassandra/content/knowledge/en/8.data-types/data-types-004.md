# text, varchar, ascii, and Unicode in Apache Cassandra

When designing **wide-column** tables in Apache Cassandra, a string column can hold a display name, an identifier, a language tag, user input, or part of a **partition key / clustering key**. Choosing `text`, `varchar`, or `ascii` is not merely a decision about which characters can be stored. When a string participates in a key, **Unicode encoding and normalization** determine whether two seemingly identical requests locate the exact same row.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. In distributed Cassandra, a sound string type choice must support **query-driven table design**, clear partition keys, CQL operations, and Java connectivity. Read/write consistency levels, replication, compaction, repair, and retries cannot fix errors caused by an application generating two distinct keys due to differences in letter casing, Vietnamese diacritics, or Unicode representation forms.

## 1. Comparing text, varchar, and ascii

| Criterion | `text` | `varchar` | `ascii` |
|---|---|---|---|
| Character set | Unicode, UTF-8 encoded | **Synonym for `text`** in Cassandra | 7-bit ASCII characters only |
| Vietnamese with diacritics, Japanese, emoji | Yes | Yes | No |
| ASCII strings like `"SKU-001"` | Yes | Yes | Yes |
| Length limit syntax `varchar(255)` | Not applicable | **Does not support length limits like traditional SQL** | Not applicable |
| Java Driver 4.x | `String` | `String` | `String` |
| Preferred usage | Content that may contain Unicode | Equivalent to `text`, useful when readers prefer SQL familiarity | Codes **guaranteed to contain only ASCII** |
| Common pitfalls | Confusing locale collation order; unnormalized keys | Assuming `varchar` caps character count | User enters accents/emoji, causing type-mismatch failures |

**Technical conclusion:** `text` and `varchar` are **aliases** for the exact same UTF-8 string type in Cassandra. There is no difference in precision, Unicode support, or searchability between these two names. `ascii` represents a narrower character set and must not be used for Vietnamese full names or descriptions.

String types do not do the job of **`uuid`**, **`timestamp`**, **`inet`**, or **`blob`**. For example, binary UUID identifiers should use `uuid` when systems agree on the format; if an "ID" is a code like `"000127"` with leading zeros, **`text`** or `ascii` is what preserves its meaning.

## 2. Unicode and UTF-8: What Cassandra Actually Stores

### 2.1. Characters, Code Points, and Byte Counts Differ

Unicode is an abstract character encoding standard; UTF-8 is one encoding of Unicode into bytes. Cassandra stores `text`/`varchar` in UTF-8, where a valid Unicode code point is encoded into **1–4 bytes**.

| Example | Meaning | Typical UTF-8 Size |
|---|---|---:|
| `A` | ASCII character U+0041 | 1 byte |
| `é` | U+00E9, precomposed Latin letter with accent | 2 bytes |
| `ệ` | U+1EC7, Vietnamese letter | 3 bytes |
| `😀` | U+1F600, emoji | 4 bytes |
| `e` + combining mark `◌́` | Two code points rendered as one accented letter | 1 + 2 = 3 bytes before normalization |

To users, multiple code points can render as **one grapheme cluster**. For example, a family emoji may consist of multiple joined code points, and an accented letter can be represented as a base letter plus a combining mark.

Therefore, there are **at least three different ways to measure length**:

1. **UTF-8 byte count**: directly relates to encoded storage size and payload limits.
2. **Unicode code point count**: number of abstract character units.
3. **Grapheme cluster count**: corresponds to the perceived character length seen by users.

Applications must pick the right unit during validation. Java's `String.length()` **counts UTF-16 code units**, not UTF-8 bytes, and does not always equal the number of code points.

~~~java
import java.nio.charset.StandardCharsets;

String emoji = "😀";
System.out.println(emoji.length());                     // 2 UTF-16 code units
System.out.println(emoji.codePointCount(0, emoji.length())); // 1 code point
System.out.println(emoji.getBytes(StandardCharsets.UTF_8).length); // 4 bytes
~~~

You cannot assume "100 Java characters = 100 bytes in Cassandra." For Vietnamese text or emoji, the UTF-8 byte length is typically larger than the visible character length.

### 2.2. text/varchar Is Not SQL's varchar(n)

In some RDBMSs, `VARCHAR(255)` declares a string column capped at 255 characters. Cassandra CQL uses `varchar` purely as an alias for `text`; **do not declare `varchar(255)`** to enforce a length constraint.

~~~cql
CREATE TABLE simple_profiles_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    biography varchar,
    language_tag ascii
);
~~~

Both `display_name` and `biography` support Unicode. If you want names capped at 80 code points or biographies at 2,000 UTF-8 bytes, the application must actively validate them. Cassandra does not enforce any business length limit based on the name `varchar`.

Operationally, a column without a `varchar(n)` cap **does not mean you should store arbitrarily long strings**: oversized cells and partitions increase network transfer, memory allocation, read/write latency, compaction, and repair overhead. For large content like documents, files, images, or large logs, consider storing objects in dedicated object storage and keeping only IDs/paths and metadata in Cassandra.

## 3. What Is ascii, and When Is It Useful?

Basic **ASCII** covers characters from U+0000 to U+007F, such as unaccented Latin letters `A-Z`, `a-z`, digits `0-9`, punctuation, and some control characters. Strings like `"vi-VN"`, `"USD"`, and `"SKU-001"` use ASCII only. Characters like `à`, `ễ`, `đ`, or emoji **do not belong to ASCII**.

Choose `ascii` when the data contract **strictly guarantees ASCII only**, for example:

- Currency codes `USD`, `VND`, `EUR` following an unaccented Latin format.
- Protocol version codes or technical status codes restricted to ASCII.
- Internal classification codes or SKUs where policy restricts the character set to ASCII with no plan to expand to Unicode.

However, `ascii` itself **does not validate business structure**. An `ascii` column does not guarantee that a currency code is exactly three uppercase letters or that a SKU contains only `[A-Z0-9-]`. Regex checks, allowed code lists, and case rules must still be enforced in the application.

~~~cql
CREATE TABLE products_by_store_sku (
    store_id uuid,
    sku ascii,
    title text,
    description varchar,
    PRIMARY KEY ((store_id), sku)
);
~~~

This table works well if the system **guarantees SKUs are ASCII**. A product name like `"Cà phê sữa đá ☕"` belongs in `title text`; it cannot be moved to `ascii`.

**Do not pick ascii solely hoping to save storage:** an ASCII character stored in UTF-8 also takes 1 byte in `text`. The main distinction is the **allowed character set**, not a guaranteed compression gain. If data can originate from global users, `text` is usually the lower-risk choice.

## 4. Unicode Normalization: The Same Letter Can Produce Two Different Keys

### 4.1. What Are NFC and NFD?

In Unicode, a single visual character can be represented by multiple **canonically equivalent** code point sequences. For example, the letter `é` can be:

- **NFC** (precomposed form): U+00E9, a single code point `é`.
- **NFD** (decomposed form): U+0065 `e` plus U+0301 (combining acute accent).

Both strings may render identically on screen yet **have different UTF-8 bytes**. When used in keys, Cassandra distinguishes strings with different bytes; it does not automatically apply NFC before hashing a partition key or comparing clustering keys.

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String composed = "\u00E9";  // U+00E9
String decomposed = "e\u0301"; // U+0065 + U+0301

System.out.println(composed.equals(decomposed)); // false
System.out.println(Arrays.equals(
    composed.getBytes(StandardCharsets.UTF_8),
    decomposed.getBytes(StandardCharsets.UTF_8)
)); // false

String normalized = Normalizer.normalize(decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
~~~

If one application writes a username in NFC while another searches using NFD, key lookups will miss the row. Practical consequences include duplicate accounts with identical display names, cache misses, data scattered across different partitions, and reconciliation failures across systems.

**Rule:** for **text key fields**, pick a normalization policy and apply it **consistently before every INSERT, SELECT, UPDATE, DELETE, and cache key generation**. NFC is a practical default for most text workloads; NFKC alters compatibility characters and should only be used when explicitly intended by business rules.

### 4.2. Unicode Normalization Is Not Case Handling

NFC **does not** make `"Lan"` and `"lan"` equal. Likewise, `"Hoa"` and `"Hòa"` remain distinct strings. If usernames must be **case-insensitive**, the application needs a policy to derive a canonical `username_key` from input.

~~~java
import java.text.Normalizer;
import java.util.Locale;

static String canonicalUsername(String raw) {
    String nfc = Normalizer.normalize(raw, Normalizer.Form.NFC);
    String lower = nfc.toLowerCase(Locale.ROOT);
    return Normalizer.normalize(lower, Normalizer.Form.NFC);
}
~~~

This illustrates a **simple lowercasing policy**. Full Unicode case-insensitive matching may require dedicated *Unicode case folding*, especially for locale-specific edge cases. Define valid username characters, whether leading/trailing whitespace is allowed, and diacritic sensitivity rules, then test with international inputs.

Never strip Vietnamese diacritics or equate visually similar characters automatically. **Unicode normalization**, **lowercasing**, **transliteration**, and **confusable filtering** are distinct rules that can destroy information if applied indiscriminately.

### 4.3. Display and Lookup Need Two Data Roles

A typical design includes:

- `username_key text`: normalized according to the identity policy; used for lookups and keys.
- `display_name text`: the user's display name, preserving casing, diacritics, and formatting.
- `bio varchar`: free-form Unicode description.
- `locale_tag ascii`: language/locale tag in ASCII if the input contract enforces it.

Do not use free-form display names as IDs: users change names, names collide, and diacritic normalization varies across sources.

## 5. Query-Driven Table Design with Text Keys

Suppose the business requirement is: **"Look up an account within a tenant by username, case-insensitively per defined policy."** A suitable schema:

~~~cql
CREATE TABLE user_handles_by_tenant (
    tenant_id uuid,
    username_key text,
    user_id uuid,
    display_name text,
    bio varchar,
    locale_tag ascii,
    PRIMARY KEY ((tenant_id, username_key))
);
~~~

The two columns `tenant_id` and `username_key` form a **composite partition key**. Cassandra hashes the encoded key bytes to distribute partitions across nodes; identity lookups must supply **both components**:

~~~cql
SELECT user_id, display_name, bio, locale_tag
FROM user_handles_by_tenant
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND username_key = 'nguyen.ha';
~~~

Example inserting Unicode data and using a lightweight transaction to claim an unclaimed handle:

~~~cql
INSERT INTO user_handles_by_tenant (
    tenant_id, username_key, user_id, display_name, bio, locale_tag
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'nguyen.ha',
    22222222-2222-4222-8222-222222222222,
    'Nguyễn Thị Hà',
    'Thích cà phê ☕ và sách của O''Reilly',
    'vi-VN'
) IF NOT EXISTS;
~~~

In CQL string literals, a single quote inside a string is escaped as **two single quotes**: `O''Reilly`. When using the Java Driver with prepared statements, **bind values** rather than concatenating and escaping strings manually.

`IF NOT EXISTS` is a conditional operation (LWT/Paxos) that prevents two racing requests with the exact same **normalized key** from creating two accounts on that key simultaneously. It **does not** prevent distinct keys caused by inconsistent normalization, nor does it turn concurrent writes across multiple tables into a single distributed transaction. Always inspect the `[applied]` result before reporting that a username was claimed.

**Key design point:** because the partition key includes the username, this table serves **exact lookups** and is ineffective for "listing all users in a tenant" when only `tenant_id` is known. That requirement needs a separate read table with an appropriate partition key/bucket. Cassandra commonly models multiple tables around **query patterns**; changing `username_key` from `text` to `ascii` does not create a new query path.

### 5.1. Case-Sensitive Keys and Distribution

If the system fails to normalize, values like `"Lan"`, `"lan"`, `"Lân"`, and `"La\u0302n"` become distinct keys even though some look similar. Cassandra does not apply **locale collation** or diacritic-insensitive matching on `text` keys by default.

Because the partition key is hashed from **key bytes**, different byte sequences produce different tokens and route to different replicas/ranges. Replication copies **whichever keys the application wrote**; it never merges variants that users consider the same name.

If usernames can be renamed, do not treat changing a partition key like updating a normal column. It typically requires creating a record under the new key, coordinating references/reservations, and handling the old record under a consistent policy.

## 6. Unicode, String Classification, and Sort Order

A common requirement is returning lists in **Vietnamese alphabetical order**. Cassandra does not have built-in *locale-aware collation* like some RDBMS collation configurations. Key string comparison is based on type and encoded bytes, **not** Vietnamese dictionary collation rules.

Consider the table:

~~~cql
CREATE TABLE products_by_category_title (
    category_id uuid,
    title_key text,
    product_id uuid,
    display_title text,
    PRIMARY KEY ((category_id), title_key, product_id)
) WITH CLUSTERING ORDER BY (title_key ASC, product_id ASC);
~~~

This table can read products by `category_id` in **clustering** order on `title_key`. However, `title_key` must be generated under a stable policy; UTF-8 byte order **does not equal Vietnamese linguistic ordering**. Casing, combining characters, and diacritics can yield results different from user expectations.

If Vietnamese sorting is required for display, you can compute a **sort key** using an explicitly chosen collation algorithm in the application, or use a dedicated search engine. Sort keys must be generated and stored consistently alongside the algorithm/version; upgrading the collation library may require rebuilding stored sort keys.

Moreover, Cassandra only supports `ORDER BY` on **clustering columns** within an appropriate key model; you cannot arbitrarily write `ORDER BY display_title` on a non-key data column as in a relational database.

**Search is not key lookup:** queries like "title contains `cà phê`", "fuzzy typo matching", "accent-insensitive search", or "full-text search" require an indexing/search strategy suited to the Cassandra version and workload, or a separate search system. Simply switching `varchar` to `text` will not provide those features.

## 7. Java Driver 4.x: Safe String Reading, Writing, and Normalization

Java Driver 4.x maps all three CQL types—**`text`**, **`varchar`**, and **`ascii`**—to Java **`String`**, using `setString` and `getString`. Although they share the same Java type, their **semantics and valid bounds** are still governed by the schema and domain contract.

Below, assume `session` is a `CqlSession` already connected to the target keyspace:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.Locale;
import java.util.UUID;

UUID tenantId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID userId = UUID.fromString("22222222-2222-4222-8222-222222222222");

String rawUsername = "Nguyen.Ha";
String usernameKey = Normalizer.normalize(
    Normalizer.normalize(rawUsername, Normalizer.Form.NFC)
        .toLowerCase(Locale.ROOT),
    Normalizer.Form.NFC
);

// Example limit: normalized key must not exceed 128 UTF-8 bytes.
if (usernameKey.getBytes(StandardCharsets.UTF_8).length > 128) {
    throw new IllegalArgumentException("Username is too long");
}

String displayName = "Nguyễn Thị Hà";
String bio = "Thích cà phê ☕ và sách của O'Reilly";
String localeTag = "vi-VN"; // Contract guarantees ASCII only.

PreparedStatement insert = session.prepare(
    "INSERT INTO user_handles_by_tenant "
  + "(tenant_id, username_key, user_id, display_name, bio, locale_tag) "
  + "VALUES (?, ?, ?, ?, ?, ?) IF NOT EXISTS");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, tenantId)
    .setString(1, usernameKey)
    .setUuid(2, userId)
    .setString(3, displayName)
    .setString(4, bio)
    .setString(5, localeTag)
    .build();

Row appliedRow = session.execute(bound).one();
if (appliedRow == null || !appliedRow.getBoolean("[applied]")) {
    throw new IllegalStateException("Username already exists or was not created");
}
~~~

In production, handle timeouts and cases where **it is unknown whether the LWT succeeded**: retry using the same `tenantId`, `usernameKey`, and `userId`, and inspect the outcome per business rules. Never assume every `[applied] = false` means a network error, or that `[applied] = true` proves related tables were also updated.

Queries must always apply the exact same normalization policy:

~~~java
String inputToSearch = "NGUYEN.HA";
String lookupKey = Normalizer.normalize(
    Normalizer.normalize(inputToSearch, Normalizer.Form.NFC)
        .toLowerCase(Locale.ROOT),
    Normalizer.Form.NFC
);

PreparedStatement find = session.prepare(
    "SELECT user_id, display_name, bio "
  + "FROM user_handles_by_tenant "
  + "WHERE tenant_id = ? AND username_key = ?");

Row found = session.execute(find.bind(tenantId, lookupKey)).one();
if (found != null) {
    UUID id = found.getUuid("user_id");
    String name = found.getString("display_name");
    String biography = found.getString("bio");
}
~~~

**Prepared statements** pass string values as bound parameters: you avoid manual SQL/CQL string concatenation and quote escaping, while reducing injection risk. The **normalization** policy still runs in the application prior to binding.

### 7.1. Validating ASCII in Java

When a column is declared `ascii`, validate proactively before calling the driver:

~~~java
static boolean isAscii(String value) {
    return value.codePoints().allMatch(cp -> cp <= 0x7F);
}

System.out.println(isAscii("USD"));       // true
System.out.println(isAscii("vi-VN"));     // true
System.out.println(isAscii("Tiếng Việt")); // false
~~~

This only checks **ASCII-only characters**. For currency codes, add rules such as `[A-Z]{3}` and validate against an allowlist; do not rely solely on `isAscii`.

### 7.2. Byte Limits, Code Points, and Visible Character Counts

~~~java
import java.nio.charset.StandardCharsets;

String title = "Học Cassandra 😀";

int utf16Units = title.length();
int codePoints = title.codePointCount(0, title.length());
int utf8Bytes = title.getBytes(StandardCharsets.UTF_8).length;

System.out.printf("UTF-16=%d, code points=%d, UTF-8 bytes=%d%n",
    utf16Units, codePoints, utf8Bytes);
~~~

When technical limits relate to storage footprint, measure **UTF-8 bytes after normalization**. When UX limits specify "display name up to 30 visible characters," count **grapheme clusters** under appropriate Unicode rules; `codePointCount` is still inaccurate for certain emoji sequences and combining marks.

In addition, Java `String` uses UTF-16 and can contain unpaired surrogates from malformed input. For inputs requiring strict Unicode integrity, validate well-formedness **before** UTF-8 encoding rather than assuming every UTF-16 string is a valid sequence of Unicode scalar values.

## 8. Common String Query Pitfalls

| Scenario | Problem | Solution |
|---|---|---|
| Using `ascii` for the name `"Đặng"` | Data is not valid ASCII | Use `text`/`varchar` |
| Thinking `varchar(255)` is valid CQL syntax | Cassandra `varchar` has no length-limit parameter | Use `varchar` or `text`, validate length in the application |
| Writing NFC username, querying NFD username | Different bytes, different key values | Normalize identically before writes and reads |
| Writing `"Lan"`, querying `"lan"` | Case mismatch | Derive a case-insensitive `username_key` if required by the domain |
| Assuming `text` sorts in Vietnamese dictionary order | Ordering is not locale-collated | Build a sort key or use collation tooling as needed |
| Using `String.length()` to enforce a byte limit | UTF-16 code units do not equal UTF-8 bytes | Measure `getBytes(UTF_8).length` after normalization |
| Choosing `text` expecting fuzzy search | String type does not enable full-text search | Design indexes/search suited to the workload |
| Using display name as primary key | Users rename, names collide, normalization is tricky | Use a stable ID and separate a normalized lookup key |
| Interpolating user values into CQL literals | Escaping bugs, injection risk | Use prepared statements and parameter binding |
| Using `text` for very large payloads or files | Inflates memory, network, SSTables, and compaction cost | Offload to object storage and store metadata/URI where appropriate |

## 9. Partition Size, Consistency, and Operational Impact

### 9.1. String Keys Can Alter Data Distribution

Cassandra assigns partitions based on the **encoded and hashed partition key**. If two strings differ in UTF-8 bytes, they are two distinct keys even if they look nearly identical on screen. Issues commonly surface when:

- One Java service normalizes to NFC while another does not.
- One service calls `trim()` on usernames while another preserves spaces.
- One data source treats usernames as case-insensitive while another is case-sensitive.
- Systems use different versions of Unicode/case-folding algorithms.

Every client reading and writing the same domain must share **one versioned, testable canonicalization contract**. For data requiring uniqueness, design proper key reservation and race handling rather than relying on default collation.

### 9.2. Long Strings, Wide Partitions, and Deletions

UTF-8 byte counts for usernames are small, but long descriptions or text fields holding large JSON blobs inflate row size. Across millions of rows, payload size and cell metadata affect bandwidth, caching, reads/writes, and compaction. Deleted or TTL-expired values generate tombstones; the `text` type itself does not prevent reads from scanning many tombstones.

If a table uses `tenant_id` alone as the partition key and holds millions of users in one partition, even short names will create an oversized partition. Avoid this by distributing rows by query, bucketing/sharding as needed, and checking real data distribution. In `user_handles_by_tenant`, the `(tenant_id, username_key)` partition key distributes lookups well, though it does not serve whole-tenant listing scans.

### 9.3. Replication and Repair Do Not Replace Normalization

Replication maintains copies of data and consistency levels govern read/write acknowledgments. Repair synchronizes replica state; compaction reorganizes SSTables. All of them operate on the **keys and values actually written** and never automatically merge:

- `"Hà"` with `"Ha\u0300"` when callers failed to normalize consistently;
- `"USER01"` with `"user01"` when the app intended case-insensitivity;
- an old username and a new username after a rename.

Any change to the normalized key policy may require a **data migration**: creating a new table/key, backfilling from trusted sources, coordinating dual-read/dual-write appropriately, and handling duplicates. Never arbitrarily alter key column types or swap normalization algorithms while other services still run an older version.

## 10. Practice Exercises

### Exercise 1 — Choosing Data Types

Given these columns: customer name `"Trần Thị Mỹ"`, currency code `"VND"`, product code `"0000185"`, a description containing emoji, and an email address with Unicode characters in the local-part.

**Hint:**

- Customer name, description, and internationalized email may require `text`/`varchar` (actual support for Unicode email addresses also depends on email standards and policy).
- Currency code can use `ascii` with valid-code checks; `text` can hold the exact same values.
- Product code is an **identifier string**, not an integer; use `ascii` if policy restricts it to ASCII, or `text` if the character set may expand.

### Exercise 2 — Identical-Looking Strings That Miss Queries

Data is written with `username_key = "café"` in NFC form. A client queries using `"cafe\u0301"` in NFD form. Why can the partition-key lookup miss the row? Write the Java normalization call.

**Answer:** the UTF-8 bytes of the two strings differ. Before both writes and queries, call:

~~~java
String key = Normalizer.normalize(input, Normalizer.Form.NFC);
~~~

If the domain also requires case-insensitivity, apply a consistent casing policy in addition to NFC normalization.

### Exercise 3 — How Long Is the String?

The string `"😀"` has `length() == 2`, `codePointCount(...) == 1`, and UTF-8 byte length 4. For a limit of "at most 64 bytes in a key," which measurement do you use?

**Answer:** UTF-8 byte count **after normalization**. For a requirement of "64 visible characters," count grapheme clusters rather than UTF-16 code units or code points alone.

### Exercise 4 — A New Query

The table `user_handles_by_tenant` uses partition key `(tenant_id, username_key)`. The product now needs to list the 50 newest users for a tenant. Can you solve this simply by changing `username_key` from `text` to `varchar`?

**Answer:** no, because `text` and `varchar` are identical. You need a new query model, such as a table partitioned by tenant + bucket with clustering keys on creation timestamp + user ID, along with controls for partition growth.

## 11. Checklist Before Deploying String Columns in Cassandra

- [ ] Does the column require Unicode, or is **ASCII** guaranteed by the input contract?
- [ ] Does the team understand that `text` and `varchar` are **equivalent**, with no SQL-style `varchar(n)`?
- [ ] For text keys, have **NFC/NFD, casing policy, whitespace, diacritics, and allowed character sets** been defined?
- [ ] Do all write/read/delete/cache paths call the exact same **canonical key** builder?
- [ ] Are limits specified in **UTF-8 bytes**, code points, or grapheme clusters matching the requirement?
- [ ] Are **display text** and **lookup/sort keys** separated to avoid losing diacritics or presentation details?
- [ ] Do critical queries supply the full partition key and use appropriate clustering columns when ordering is needed?
- [ ] If full-text or fuzzy search is needed, has an indexing/search strategy been chosen for the Cassandra version and real workload?
- [ ] Does the Java Driver bind `String` via prepared statements, with proper ASCII/UTF-8 and null checks?
- [ ] Have large text fields, partition sizes, and a migration strategy for normalization policy changes been addressed?
- [ ] For unique username registration, have race conditions, retries, and cross-table consistency been designed?

**Remember:** `text` and `varchar` both store UTF-8 Unicode strings; `ascii` accepts ASCII only. Whenever a string participates in a **partition key or clustering key**, treat **normalization/canonicalization** as part of the data model and Java application contract. Cassandra distributes and compares the actual encoded keys; replication, repair, compaction, and consistency levels will never treat two visually similar strings as one identifier on their own.
