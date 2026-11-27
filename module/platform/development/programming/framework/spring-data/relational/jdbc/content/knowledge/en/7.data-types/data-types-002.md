# Strings, Unicode, Column Length, and Empty Data

In a **Spring Data Relational JDBC (Spring Data JDBC)** application, string values pass through multiple layers before becoming data in a table: from a Java `String`, through the JDBC driver, to a `VARCHAR` or `TEXT` column in PostgreSQL/MySQL. The exact same value visible on screen can have different byte counts, Unicode character counts, and Java lengths; furthermore, `null`, an empty string, and a whitespace-only string each carry distinct meanings.

This lesson guides you on choosing column types, storing Vietnamese text and emojis with proper Unicode, setting reasonable length limits, designing rules for empty data, and mapping those decisions into Spring Data JDBC entities and repositories.

## 1. Four Questions Before Adding a String Column

Suppose a system stores customer display profiles. Each profile has a display name, a nickname, a short bio, and a language tag.

| Field | Business Question | Illustrative Decision |
|---|---|---|
| `displayName` | Is a name required? How should the name be limited? | Required, not whitespace-only, maximum 80 characters |
| `nickname` | Is having no nickname valid? | Optional; use `NULL` when not set |
| `bio` | Do we need to distinguish “not written yet” from “cleared to empty”? | Allow both `NULL` and `''` if required by business rules |
| `localeTag` | Which language and region is chosen for display? | Short string, e.g., `vi-VN`, required |

These decisions belong to **the data model and business domain** before choosing annotations. Allowing `NULL` in a column does not mean the application automatically knows the difference between “user has not entered anything” and “user intentionally deleted it”; that meaning must be defined at the API and business layers.

~~~mermaid
flowchart LR
    Input["Input Form / JSON"] --> Rules["Business rules<br/>trim/normalize/validate"]
    Rules --> Entity["Java String<br/>or null"]
    Entity --> Repo["Spring Data JDBC<br/>Repository"]
    Repo --> Driver["JDBC driver"]
    Driver --> Column[("VARCHAR / TEXT<br/>NULL, charset, collation")]
    Column -->|"read"| Repo
~~~

In this flow, **input normalization and validation** should occur before calling the repository; the **database** still needs constraints to block invalid data from other write sources.

## 2. Common String Types in Relational Databases

| SQL Type | Characteristics | When to Use | What to Watch Out For |
|---|---|---|---|
| `CHAR(n)` | Fixed length, with character padding | Codes with truly fixed length | Trailing space padding and comparisons vary by DBMS; avoid for people's names |
| `VARCHAR(n)` | Variable-length string with limit `n` | Names, SKUs, emails, language codes | Must know whether `n` counts characters or bytes and understand DB row-size byte limits |
| `TEXT` | Long string without declaring `n` in type syntax | Descriptions, notes, free-form content | Storage limits, indexing capabilities, and storage mechanics vary by DB |

**PostgreSQL:** `VARCHAR(n)` limits the number of characters; `TEXT` has no declared `n` limit and is very commonly used for text. `CHAR(n)` is space-padded to the specified length.

**MySQL 8.x:** `VARCHAR(n)` limits by character count, though it is still subject to row-size limits and byte counts per character set. `TEXT` is typically used for long paragraphs, but standard `TEXT` is limited to roughly **65,535 bytes** (the practical content limit may also account for overhead); longer data may require `MEDIUMTEXT` or `LONGTEXT` as needed. `CHAR(n)` is likewise unsuitable for variable-length names and descriptions.

**Do not pick `TEXT` just to avoid thinking about limits.** A bio field can be stored in `TEXT`, yet the API should still enforce reasonable length limits for UI, search, and storage volume. Conversely, a `VARCHAR(80)` column does not automatically ensure that the input is meaningful or not entirely whitespace.

## 3. Unicode, UTF-8, UTF-16, and Length Are Different Concepts

**Unicode** assigns code points to characters. **UTF-8** and **UTF-16** are encodings that represent those code sequences as storage units. Java `String` uses **UTF-16 code units**, whereas PostgreSQL/MySQL typically store text using **UTF-8** encoding (with MySQL, use `utf8mb4` for full Unicode support).

There are at least four ways to measure “length”:

1. **Bytes:** the number of bytes when encoding the string, e.g., UTF-8; relevant to storage size, column type limits, and data transmission.
2. **UTF-16 code units:** the unit counted by Java's `String.length()`. An emoji outside the BMP typically takes **2** units.
3. **Unicode code points:** the count of Unicode code points, countable via `String.codePointCount(...)`.
4. **Grapheme clusters:** character clusters perceived by a user as a single symbol; may consist of multiple code points such as combined emojis or base letters with combining accents.

| Content | `String.length()` | Code points | `CHAR_LENGTH` in UTF-8 SQL | UTF-8 Bytes |
|---|---:|---:|---:|---:|
| `A` | 1 | 1 | 1 | 1 |
| `ế` (precomposed single code point) | 1 | 1 | 1 | 3 |
| `🚀` | 2 | 1 | 1 | 4 |
| `e + ◌́` (letter `e` and combining acute accent) | 2 | 2 | 2 | 3 |
| `👩‍💻` (ZWJ combined emoji) | 5 | 3 | 3 | 11 |

In the table above, `CHAR_LENGTH` refers to the SQL function on UTF-8 encoded data in PostgreSQL/MySQL; it measures **characters as implemented by the DB**, not user-perceived graphemes. The string `👩‍💻` usually renders as one emoji yet contains three code points.

Java example:

~~~java
import java.nio.charset.StandardCharsets;

String rocket = "🚀";
System.out.println(rocket.length());                         // 2 UTF-16 units
System.out.println(rocket.codePointCount(0, rocket.length())); // 1 code point
System.out.println(rocket.getBytes(StandardCharsets.UTF_8).length); // 4 bytes

String joinedEmoji = "👩‍💻";
System.out.println(joinedEmoji.length()); // 5 UTF-16 units
System.out.println(joinedEmoji.codePointCount(
    0, joinedEmoji.length()
)); // 3 code points
~~~

Therefore, if `display_name VARCHAR(80)` specifies 80 characters, checking `displayName.length() <= 80` in Java **is not strictly equivalent** to how the DB limits characters. Using `codePointCount` is usually better when aligning with a column limit by code points; if the policy targets user-perceived “visible characters”, a **grapheme cluster** segmentation algorithm is required, not just code points.

### The Same Letter Can Be Encoded in Two Ways

The letter `é` can be:

- **Precomposed form:** a single code point `U+00E9`.
- **Decomposed (combining) form:** `e` (U+0065) + acute accent (U+0301).

Two strings may look identical yet differ in code point count, byte count, and binary comparison. Depending on business rules, you can normalize to **Unicode NFC** before checking limits and saving.

~~~java
import java.text.Normalizer;

String decomposed = "e\u0301";
String composed = Normalizer.normalize(
    decomposed, Normalizer.Form.NFC
);

System.out.println(decomposed.length());  // 2
System.out.println(composed.length());    // 1
System.out.println(composed.equals("é")); // true
~~~

Unicode normalization is **not** stripping Vietnamese diacritics. NFC preserves accented characters while unifying equivalent representations. Accent-insensitive or case-insensitive searching is a **separate** decision related to collation or search algorithms.

## 4. Configuring Unicode Storage and Transmission in PostgreSQL or MySQL

### PostgreSQL: Database and UTF8 Connection

PostgreSQL stores strings according to the **database encoding**. When using Vietnamese or emojis, choose a database with `UTF8` encoding. You can inspect the connection:

~~~sql
SHOW server_encoding;
SHOW client_encoding;

SELECT
    CHAR_LENGTH('Tiếng Việt 🚀') AS characters,
    OCTET_LENGTH('Tiếng Việt 🚀') AS bytes_utf8;
~~~

A properly configured UTF-8 environment will show `server_encoding = UTF8` and `client_encoding = UTF8`. The PostgreSQL JDBC driver handles converting Java strings over the connection protocol and encoding; there is no need to manually encode display names into bytes and store them in `VARCHAR`.

When initializing a new database, encoding is set at database creation time, such as `CREATE DATABASE jdbc_lab ENCODING 'UTF8';` in environments that support that configuration. Changing the encoding of an existing database is not as simple as running `ALTER TABLE`.

### MySQL: Use utf8mb4 and Intentional Collation

In MySQL, configuring **character set** and **collation** are two separate concerns:

- `utf8mb4` defines the character set capable of storing Unicode characters, including 4-byte emojis.
- `utf8mb4_0900_ai_ci` is an **accent-insensitive** and **case-insensitive** collation in MySQL 8.0+/8.4; it affects comparison, sorting, and uniqueness on columns using that collation.

You can create a database for a learning environment:

~~~sql
CREATE DATABASE jdbc_lab
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
~~~

If the database already exists, do not re-run `CREATE DATABASE` as a migration step. Check the current configuration instead:

~~~sql
SHOW CREATE DATABASE jdbc_lab;
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
~~~

When creating tables, you can explicitly specify `DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci`. For the MySQL CLI tool, use a connection with appropriate UTF-8 encoding, such as the `--default-character-set=utf8mb4` option; also save `.sql` files in UTF-8.

**Common mistake:** using MySQL's `utf8` charset in older configurations, which actually only supports up to three bytes per character (`utf8mb3`). In that case, 4-byte emojis cannot be stored properly. For new applications, choose `utf8mb4`.

### Character Set Does Not Determine Every Comparison

For example, MySQL with `utf8mb4_0900_ai_ci` may treat names differing in letter case or accents as equivalent in comparisons. PostgreSQL has a different collation mechanism; behavior depends on the active collation.

If a column holds a **unique username/technical code**, define an explicit comparison policy and unique index for that column. Do not assume that `"Hoa"`, `"hoa"`, and `"Hòa"` are always treated as three distinct names in every database.

## 5. Sample Table Design: Name, Nickname, Bio, and Language

The two schemas below express the same business contract. **Choose one** based on the DBMS you are using. The `CREATE TABLE` statements are intended for a practice database and assume the table does not exist yet.

### PostgreSQL

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    nickname VARCHAR(40),
    bio TEXT,
    locale_tag VARCHAR(16) NOT NULL DEFAULT 'vi-VN',

    CONSTRAINT ck_profile_display_name
        CHECK (BTRIM(display_name) <> ''),
    CONSTRAINT ck_profile_nickname
        CHECK (nickname IS NULL OR BTRIM(nickname) <> '')
);
~~~

### MySQL 8.4

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    nickname VARCHAR(40) NULL,
    bio TEXT NULL,
    locale_tag VARCHAR(16) NOT NULL DEFAULT 'vi-VN',

    CONSTRAINT ck_profile_display_name
        CHECK (TRIM(display_name) <> ''),
    CONSTRAINT ck_profile_nickname
        CHECK (nickname IS NULL OR TRIM(nickname) <> '')
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
~~~

Explanation of decisions:

- **`display_name VARCHAR(80) NOT NULL`:** requires a string and rejects strings longer than the column limit.
- **`nickname VARCHAR(40) NULL`:** allows **`NULL`** to represent “no nickname set”.
- **`bio TEXT NULL`:** allows storing Unicode paragraphs; in this example, `NULL` and `''` are two distinct states.
- **`locale_tag VARCHAR(16) NOT NULL DEFAULT 'vi-VN'`:** stores the language/region tag as text. The DB default value is only used when an INSERT **omits the column** or requests `DEFAULT`, not when INSERT explicitly specifies `NULL`.
- **`CHECK`:** provides extra protection against names/nicknames consisting solely of ordinary spaces. Default `TRIM` / `BTRIM` functions **do not filter every kind of Unicode whitespace**. The application needs additional validation if business rules treat tabs, newlines, or special whitespace characters as blank.

This example does not add a `UNIQUE` constraint on `display_name` because multiple people can share the same name. If unique identification is required, use an appropriate field such as username/user ID with an explicit collation policy.

## 6. Sample Data Containing Vietnamese, Unicode, and Empty Values

Save the script as **UTF-8** and execute it after the table has been created:

~~~sql
INSERT INTO customer_profiles
    (display_name, nickname, bio, locale_tag)
VALUES
    ('Nguyễn An', NULL, 'Học Spring Data JDBC 🚀', 'vi-VN'),
    ('Lê Mỹ Linh', 'Linh', '', 'vi-VN'),
    ('東京', NULL, NULL, 'ja-JP');
~~~

Within the same table, there are three cases:

1. `Nguyễn An` has `nickname = NULL` and `bio` containing an emoji.
2. `Lê Mỹ Linh` has nickname `Linh` and `bio = ''` (empty string, length 0).
3. `東京` has `nickname = NULL` and `bio = NULL` (no value stored).

Observational SQL queries:

~~~sql
SELECT
    id,
    display_name,
    CHAR_LENGTH(display_name) AS name_characters,
    OCTET_LENGTH(display_name) AS name_bytes,
    nickname,
    bio
FROM customer_profiles
ORDER BY id;

SELECT COUNT(*) AS no_bio_count
FROM customer_profiles
WHERE bio IS NULL;

SELECT COUNT(*) AS empty_bio_count
FROM customer_profiles
WHERE bio = '';
~~~

When seeded once into an empty table, both of the last two COUNT queries return **1**: one profile has `bio IS NULL`, and one profile has `bio = ''`. `CHAR_LENGTH` counts characters according to the DB; `OCTET_LENGTH` counts bytes, so accented names or multibyte characters yield two different numbers.

A query directly classifying all three states:

~~~sql
SELECT
    display_name,
    CASE
        WHEN bio IS NULL THEN 'NOT_PROVIDED'
        WHEN bio = '' THEN 'EMPTY_STRING'
        ELSE 'HAS_CONTENT'
    END AS bio_state
FROM customer_profiles
ORDER BY id;
~~~

Expected classification result: `Nguyễn An = HAS_CONTENT`, `Lê Mỹ Linh = EMPTY_STRING`, `東京 = NOT_PROVIDED`.

## 7. Distinguishing NULL, Empty Strings, and Whitespace-Only Strings

| Value in Java | Possible Stored SQL Data | Example Meaning | Query |
|---|---|---|---|
| `null` | `NULL` | Bio not entered yet | `WHERE bio IS NULL` |
| `""` | `''` | Bio intentionally left blank | `WHERE bio = ''` |
| `"   "` | String containing spaces | User entered spaces | `WHERE TRIM(bio) = '' AND bio IS NOT NULL` |
| `"Hello"` | Text with content | Bio provided | `WHERE bio IS NOT NULL AND bio <> ''` |

In PostgreSQL and MySQL, an empty string is **different** from SQL `NULL`. SQL evaluates `NULL` using three-valued logic: true, false, and **unknown**. Therefore:

~~~sql
-- CORRECT: find rows with no value yet.
SELECT * FROM customer_profiles WHERE bio IS NULL;

-- CORRECT: find rows with an empty string.
SELECT * FROM customer_profiles WHERE bio = '';

-- SEMANTICALLY WRONG: comparing to NULL using the = operator.
SELECT * FROM customer_profiles WHERE bio = NULL;
~~~

The last query returns no rows with `bio NULL` because `bio = NULL` evaluates to `UNKNOWN`. To check for null values, you must use `IS NULL` or `IS NOT NULL`.

When a default display value is needed, you can use:

~~~sql
SELECT
    display_name,
    COALESCE(nickname, '(no nickname set)') AS nickname_for_display
FROM customer_profiles;
~~~

`COALESCE` in a query **does not change the stored value**; it only returns an alternative value when the expression is `NULL`. `COALESCE(nickname, '')` also renders `NULL` as an empty string, so only use it if the UI genuinely intends to merge those two states.

### API-Layer Conventions

Suppose a client updates the `bio` field:

- JSON **without the `bio` property**: can be interpreted as “keep unchanged” in a PATCH API.
- JSON with `"bio": null`: can be interpreted as “clear value / not provided”.
- JSON with `"bio": ""`: can be interpreted as “set empty string”.

This is a **convention that must be designed for the API**, not a default behavior decided by Spring Data JDBC. A DTO with only a `String bio` property cannot on its own distinguish an “absent field” from a “null field” without a mechanism to track field presence.

For `nickname` in this lesson, the business rule deliberately **collapses empty/whitespace-only strings to `null`** before saving for data consistency. For `bio`, we preserve the distinction between `NULL` and `''`. Both choices can coexist because each field has its own meaning.

## 8. Mapping String Columns into a Spring Data JDBC Entity

Spring Data JDBC maps standard text strings to `String`. It does not require JPA's `@Entity`, and `@Column` is an annotation from **Spring Data Relational**, not `jakarta.persistence.Column`.

Example **`CustomerProfile.java`**:

~~~java
package com.example.demo.profile;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_profiles")
public record CustomerProfile(
    @Id Long id,
    @Column("display_name") String displayName,
    String nickname,
    String bio,
    @Column("locale_tag") String localeTag
) {}
~~~

Example **`CustomerProfileRepository.java`**:

~~~java
package com.example.demo.profile;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, Long> {

    List<CustomerProfile> findByDisplayName(String displayName);
}
~~~

Explanation:

- `@Table("customer_profiles")` specifies the table for this simple aggregate root.
- `@Id` specifies the primary key. When creating a new entity, set `id = null` and use the entity returned by `save(...)` to obtain the generated ID.
- `@Column("display_name")` and `@Column("locale_tag")` provide explicit mapping from Java camelCase names to snake_case column names. Fields without `@Column` can be mapped using the default naming strategy.
- Nullable fields in the table, such as `nickname` and `bio`, can be represented by a `String` holding Java `null`.
- The `findByDisplayName(...)` method is a derived query from the method name; how the DB matches names is still governed by **collation**, so do not assume it is a case-sensitive or accent-sensitive comparison.

**Very important point:** the `@Column` annotation does not create `VARCHAR(80)`, does not add `NOT NULL`, and does not normalize Unicode. In this lesson, the **SQL schema** and **business logic** are responsible for data limits/constraints. If using a migration tool like Flyway or Liquibase, manage versioned schemas rather than only editing Java annotations.

### Writing Data via Repository

~~~java
CustomerProfile incoming = new CustomerProfile(
    null,
    "Đỗ Khánh",
    null,
    "Thử lưu tiếng Việt và emoji 😀",
    "vi-VN"
);

CustomerProfile saved = repository.save(incoming);
Long generatedId = saved.id();

CustomerProfile loaded = repository.findById(generatedId)
    .orElseThrow();

System.out.println(loaded.displayName()); // Đỗ Khánh
~~~

This snippet assumes `repository` is a `CustomerProfileRepository` bean injected into a Spring Boot component. Spring Data JDBC sends string values through the JDBC driver using the framework's parameter-binding mechanism; it does not concatenate name content directly into SQL strings.

## 9. Validating and Normalizing Length Before Saving

Database limits are the final line of defense. The business layer should respond early with clear messages while enforcing policies for trimming leading/trailing whitespace and Unicode normalization.

Example of a service constructing a new entity:

~~~java
package com.example.demo.profile;

import java.text.Normalizer;
import java.text.Normalizer.Form;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProfileService {

    private final CustomerProfileRepository profiles;

    public ProfileService(CustomerProfileRepository profiles) {
        this.profiles = profiles;
    }

    @Transactional
    public CustomerProfile create(
            String displayName,
            String nickname,
            String bio) {
        String name = requiredName(displayName);
        String optionalNickname = optionalNickname(nickname);

        // Preserve distinction between bio == null and bio.equals("").
        CustomerProfile profile = new CustomerProfile(
            null, name, optionalNickname, bio, "vi-VN"
        );
        return profiles.save(profile);
    }

    private static String requiredName(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Name is required");
        }
        String value = Normalizer.normalize(raw.strip(), Form.NFC);
        int codePoints = value.codePointCount(0, value.length());
        if (value.isBlank() || codePoints > 80) {
            throw new IllegalArgumentException(
                "Name must contain 1..80 Unicode code points"
            );
        }
        return value;
    }

    private static String optionalNickname(String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }
        String value = Normalizer.normalize(raw.strip(), Form.NFC);
        if (value.isEmpty()) {
            return null;
        }
        if (value.codePointCount(0, value.length()) > 40) {
            throw new IllegalArgumentException(
                "Nickname is too long"
            );
        }
        return value;
    }
}
~~~

**Illustrative service policy:**

- The display name is required, stripped of leading/trailing whitespace using `String.strip()`, and NFC-normalized.
- A whitespace-only nickname is converted to `null`.
- Length limits are checked using **code points** after normalization, which aligns more closely with `VARCHAR` character-length semantics than `String.length()`.
- `bio` is left untouched to preserve the difference between “not entered” and “empty string”; if the product has length or content limits, add separate rules.

`String.strip()` and `String.isBlank()` use Java's definition of whitespace. They **do not cover every character that visually resembles a space**, such as certain non-breaking spaces. If stricter sanitization is needed, specify the exact character set to handle. Do not arbitrarily remove all whitespace in the middle of a name, as internal spaces can be valid content.

For fields requiring a limit on **visible user-facing characters**, code points are still not enough (combined emojis contain multiple code points). Choose a grapheme measurement algorithm suited to the product; SQL column limits and UI limits can be **two different thresholds**.

### Calculating UTF-8 Bytes If Storage Limits Require It

~~~java
import java.nio.charset.StandardCharsets;

String bio = "Học Spring Data JDBC 🚀";
int utf8Bytes = bio.getBytes(StandardCharsets.UTF_8).length;
System.out.println(utf8Bytes);
~~~

For MySQL `TEXT` columns, the byte limit can matter more than the code point count. With long input data, the application may need to check both the **business threshold** and the **technical threshold** of the column type in use.

## 10. Configuring Spring Boot Connections and Preserving UTF-8 End-to-End

Gradle dependencies for Spring Data JDBC and the database driver:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'

    // Choose the driver for the database in use.
    runtimeOnly 'org.postgresql:postgresql'
    // Or:
    // runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

Example **`application.yml`** for local PostgreSQL:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/jdbc_lab
    username: jdbc_user
    password: localdev
  sql:
    init:
      mode: never
~~~

When using MySQL, change the URL to `jdbc:mysql://localhost:3306/jdbc_lab` and use the MySQL driver. The value `localdev` is just a sample password for a learning environment; real applications should obtain connection credentials from environment variables or a secrets manager.

`spring.sql.init.mode: never` indicates that the schema and seed data will be executed separately via SQL/migrations rather than having the application re-run them on every startup. In a real project environment, initialization settings depend on how you organize migrations.

**Note on Unicode:** The JDBC driver and database are responsible for transmitting `String` values with the proper encoding. Typically, you do not need to call `new String(bytes, UTF_8)` when you already have a Java `String`. If strings become garbled or turn into `?` characters, inspect the HTTP/JSON source, SQL files, database encoding, and connection charset in sequence. Repeatedly converting bytes with the wrong encoding can corrupt data before it ever reaches the repository.

## 11. What Errors Do Empty and Oversized Data Produce?

Suppose the following commands are run in the practice database:

~~~sql
-- Blocked: display_name is required and cannot be NULL.
INSERT INTO customer_profiles (display_name, locale_tag)
VALUES (NULL, 'vi-VN');

-- Blocked: empty string fails display_name's CHECK constraint.
INSERT INTO customer_profiles (display_name, locale_tag)
VALUES ('', 'vi-VN');

-- Blocked: 81 ASCII characters exceed VARCHAR(80).
INSERT INTO customer_profiles (display_name, locale_tag)
VALUES (
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
    'vi-VN'
);

-- Valid: nickname absent, bio is an empty string.
INSERT INTO customer_profiles (display_name, nickname, bio, locale_tag)
VALUES ('Trần Lan', NULL, '', 'vi-VN');
~~~

The first three statements are **intentionally written to fail**: run each statement individually when practicing, do not paste the whole block as a migration. Exact error messages vary between PostgreSQL and MySQL: they may be `NOT NULL`, `CHECK constraint`, or `data too long for column` errors.

On the Java side, Spring typically translates driver write errors into an exception in the data-access hierarchy (such as `DataIntegrityViolationException`), though the exact exception type depends on the driver, dialect, and framework error translation. Do not rely on a specific SQL error message as an API contract; validate input data and handle errors in a controlled manner.

### Watch Out When Changing Column Length

When business rules change a name limit from 80 to 120, **do not just edit a Java constant**. A database migration is required:

~~~sql
-- PostgreSQL
ALTER TABLE customer_profiles
ALTER COLUMN display_name TYPE VARCHAR(120);
~~~

~~~sql
-- MySQL
ALTER TABLE customer_profiles
MODIFY COLUMN display_name VARCHAR(120) NOT NULL;
~~~

Also update validation, API messages, documentation, and display logic. If **shrinking** a column from 120 down to 80, evaluate existing data before running the migration because long records can cause the migration to fail or be truncated depending on the DB/SQL mode configuration.

## 12. String Comparison and Searching: Case, Accents, and Whitespace

Comparison policies cannot be determined solely from the Java `String` type or a `VARCHAR` column name. A search such as:

~~~java
List<CustomerProfile> results =
    repository.findByDisplayName("Nguyễn An");
~~~

is executed by the database and follows the column/collation's comparison rules. Several points must be decided:

- **Case sensitivity:** should `"An"` be considered equal to `"an"`?
- **Accent sensitivity:** are `"Hoa"` and `"Hòa"` two distinct values?
- **Leading/trailing whitespace:** should values be normalized to a single form before saving?
- **Unicode normalization:** are `"é"` and `"e\u0301"` handled consistently?
- **Matching for unique identifiers:** requires a canonical key or appropriate collation; do not default to using display names as unique keys.

For instance, MySQL `utf8mb4_0900_ai_ci` performs accent-insensitive and case-insensitive comparisons; PostgreSQL offers various collation choices and interpretations. If exact byte/code-point matching is required, define a dedicated comparison strategy rather than trusting the system's default collation.

Similarly, `LIKE` uses the `%` and `_` characters in SQL syntax to construct search patterns. When accepting strings from users, use queries with **bind parameters** and proper escaping instead of concatenating input directly into SQL.

## 13. Common Mistakes in Spring Data JDBC

| Design/Implementation Mistake | What Can Happen | How to Handle |
|---|---|---|
| Using `String.length()` to predict DB character count with emojis | Java counts UTF-16 code units, which differs from code points | Define the measurement goal; use `codePointCount` or graphemes as appropriate |
| Choosing MySQL `utf8mb3` / legacy `utf8` configuration | 4-byte emojis cannot be stored | Use `utf8mb4` for table/connection charset |
| Using `CHAR(n)` for variable-length names | Unwanted space padding and comparison issues | Use `VARCHAR(n)` or `TEXT` as needed |
| Treating `NULL` the same as `''` | Loses distinction between “not entered” and “cleared” | Explicitly define the meaning of each state and API contract |
| Querying `= NULL` | Fails to find rows with NULL values | Use `IS NULL` |
| Relying solely on `@Column` to enforce length/NOT NULL | Schema does not automatically receive desired constraints | Write DDL/migrations and validation |
| Allowing whitespace-only strings in required name columns | Records contain no useful content | Validate in domain/service and use appropriate CHECK constraints |
| Limiting TEXT by character count while ignoring MySQL bytes | Exceeds TEXT type limit with multibyte characters | Check byte count / column type as needed |
| Assuming string comparisons always match Java `equals` | Collation may be accent- or case-insensitive | Choose specific collation and identifier rules |
| Concatenating user names directly into SQL | SQL injection risk and escaping bugs | Use repository queries with bind parameters |

## 14. Self-Check Practice Exercises

1. Run `SELECT CHAR_LENGTH('🚀'), OCTET_LENGTH('🚀');` on PostgreSQL or MySQL with UTF-8/utf8mb4. Explain why the results are `1` and `4`, respectively.
2. Seed the three sample profiles. Query rows with `bio IS NULL` and `bio = ''` separately. Why are the two result sets different?
3. Try inserting a `display_name` with 81 `A` characters, then try inserting a name consisting only of spaces. Identify which column/constraint blocks each case.
4. Use Java to print `length()` and `codePointCount(...)` for `"🚀"`, `"e\u0301"`, and `"👩‍💻"`. Compare them with the database's `CHAR_LENGTH`.
5. Implement profile creation via `ProfileService.create(...)`; test `nickname = null`, `nickname = ""`, and `nickname = "   "`. What value is stored in all three cases according to the service rules?
6. Inspect the MySQL collation (if using MySQL) and try querying names differing in case/accents. What do the results show about why search policies cannot be inferred from `String.equals`?
7. Propose how to update a PATCH API to distinguish **field absent**, **field is null**, and **field is an empty string** when updating `bio`.

Example SQL query counting the three states of `bio`:

~~~sql
SELECT
    SUM(CASE WHEN bio IS NULL THEN 1 ELSE 0 END) AS missing_bio,
    SUM(CASE WHEN bio = '' THEN 1 ELSE 0 END) AS empty_bio,
    SUM(CASE WHEN bio IS NOT NULL AND bio <> '' THEN 1 ELSE 0 END)
        AS nonempty_bio
FROM customer_profiles;
~~~

With the initial sample data and no additional rows written, the expected result is **`missing_bio = 1`, `empty_bio = 1`, `nonempty_bio = 1`**.

The key takeaway when designing strings in Spring Data JDBC is: **Java `String`, Unicode, SQL length, and the meaning of empty data are not the same concept**. Choose column types based on content, use UTF-8/utf8mb4 to store Unicode properly, define length limits and normalization rules before writing, and preserve the distinction between `NULL` and empty strings where the business domain requires it.
