# character_set_client, character_set_connection, and character_set_results

When an application sends SQL to MySQL, string data passes through multiple conversion steps before being stored or returned. The application encodes characters into bytes using one character set; MySQL receives those bytes and interprets the statement and literals according to the session configuration; when returning results, the server may convert strings to the character set expected by the client. If both sides do not agree on how bytes are interpreted, data can become corrupted, display incorrectly, or fail to save.

Three key session variables control this path:

- **character_set_client**: the character set MySQL uses to interpret statement data received from the client.
- **character_set_connection**: the character set MySQL uses for literals after converting from character_set_client; it is also the default character set for literals in statements.
- **character_set_results**: the character set MySQL uses to convert result data before sending it back to the client.

Understanding these three variables properly helps troubleshoot Vietnamese text issues, emojis, multilingual data, SQL string literals, and results returned to the application. This article focuses on MySQL 8.x and recommends using utf8mb4 for most modern applications.

## 1. How do character sets and collations differ?

A **character set** defines the set of representable characters and how characters are encoded into bytes. For example, utf8mb4 can represent Unicode characters outside the Basic Multilingual Plane, including many emojis and supplementary characters.

A **collation** defines how strings belonging to a character set are compared and sorted. A character set can have many collations. For instance, different collations may distinguish or ignore uppercase/lowercase differences, accents, or linguistic rules in comparisons.

For example:

| Component | Example | Role |
|---|---|---|
| Character set | utf8mb4 | Represents characters as bytes |
| Collation | utf8mb4_0900_ai_ci | Rules for comparing and sorting strings |

The example collation name can be read as follows:

- utf8mb4: the character set the collation belongs to.
- 0900: the collation rule set based on UCA 9.0 in MySQL.
- ai: accent-insensitive, does not distinguish accents in comparisons.
- ci: case-insensitive, does not distinguish uppercase/lowercase in comparisons.

The character set determines whether a character can be represented; the collation determines how represented string values are compared. The two concepts are related, but cannot substitute for one another.

## 2. The path of a string through a MySQL connection

Suppose an application sends a query:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE full_name = 'Nguyễn An';
~~~

To process the Vietnamese literal in the statement and return results to the application, MySQL needs to know which character set the client used to encode the bytes and which character set the client can receive results in.

Conceptual flow:

~~~text
Application
  |
  | Encode SQL statement into bytes using client charset
  v
MySQL receives statement
  |
  | character_set_client
  | Interpret bytes sent by client
  v
Convert literals to connection charset
  |
  | character_set_connection
  | collation_connection applies to literals
  v
Parse and execute SQL
  |
  | Read data from column per column's charset/collation
  v
Convert result data
  |
  | character_set_results
  v
Application receives bytes and decodes for display
~~~

The three variables participate at different stages:

1. **Client sends:** MySQL assumes the statement bytes are encoded according to character_set_client.
2. **Server processes literals:** MySQL converts literals from character_set_client to character_set_connection; collation_connection affects string literal comparisons where applicable.
3. **Server returns:** MySQL converts result data to character_set_results if this variable is not NULL.

If the application sends UTF-8 bytes while declaring character_set_client as a different encoding, MySQL may misinterpret the bytes right from the start. If the server returns UTF-8 yet the application decodes it using a different encoding, data can display incorrectly on the client side.

## 3. character_set_client: MySQL interprets data received from the client

### 3.1. Role

character_set_client tells MySQL which character set encodes the bytes in the SQL statement sent by the client. This matters for string literals, object names with special characters, and SQL content containing non-ASCII characters.

For example, the application sends:

~~~sql
INSERT INTO customers (full_name)
VALUES ('Trần Thị Mai');
~~~

If the application actually encodes the statement in UTF-8 while the server interprets those bytes under a different character set, the literal content may be misinterpreted or trigger a conversion error.

### 3.2. Checking the current value

In a connection session:

~~~sql
SELECT @@SESSION.character_set_client;
~~~

View all three variables at once:

~~~sql
SHOW SESSION VARIABLES
WHERE Variable_name IN (
    'character_set_client',
    'character_set_connection',
    'character_set_results'
);
~~~

You can view the server-wide default value:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'character_set_client';
~~~

The SESSION value is what applies to statements running in the current connection. Changing GLOBAL does not necessarily change already-open sessions immediately.

### 3.3. When should it be changed?

In modern applications, configure the connector to send data as UTF-8 and negotiate or configure the MySQL session appropriately. With MySQL 8.x, utf8mb4 is usually the suitable choice for Unicode data.

Do not set character_set_client arbitrarily. The value must reflect the byte encoding the client actually sends. If the client sends UTF-8 while declaring latin1, switching the server to utf8mb4 after corrupted bytes have already been sent cannot recover the original content.

## 4. character_set_connection: the character set used to process literals

### 4.1. Role

After receiving a statement, MySQL converts literals from character_set_client to character_set_connection. String literals without a character set introducer typically use the connection character set and connection collation by default.

A literal can explicitly declare a character set using an introducer:

~~~sql
SELECT _utf8mb4'Tiếng Việt 🙂' AS explicit_charset_text;
~~~

An introducer specifies the character set of that literal; it does not change the three session variables and cannot repair bytes that the client encoded incorrectly before sending.

Example:

~~~sql
SELECT
    'Hello' AS greeting,
    CHARSET('Hello') AS literal_charset,
    COLLATION('Hello') AS literal_collation;
~~~

The CHARSET and COLLATION outputs let you observe the character set and collation MySQL assigns to a literal in the current session context.

### 4.2. Connection collation

The collation_connection variable accompanies character_set_connection. It determines the default collation for string literals on the connection and can affect comparison results between string expressions under MySQL's coercibility rules.

Check:

~~~sql
SHOW SESSION VARIABLES
WHERE Variable_name IN (
    'character_set_connection',
    'collation_connection'
);
~~~

Example:

~~~sql
SELECT
    COLLATION('A') AS current_collation,
    ('a' = 'A') AS equal_under_collation;
~~~

The comparison result depends on the collation applied to the expressions. Under a case-insensitive collation, the two literals can be treated as equal. Under a case-sensitive collation, the result can differ.

The column's collation remains an important part of comparisons. When an expression combines a literal with a column, MySQL applies collation resolution rules between operands; do not assume that merely changing collation_connection alters every comparison in the schema.

### 4.3. Conversion can fail

MySQL must convert strings from character_set_client to character_set_connection. If the target character set cannot represent a character, conversion may raise an error or lose information depending on the context and conversion rules.

For example, an older character set cannot represent all Unicode characters. Using utf8mb4 on both the client and connection sides helps prevent many errors when statements contain Vietnamese text, supplementary characters, or emojis.

## 5. character_set_results: the character set of returned data

### 5.1. Role

character_set_results tells MySQL which character set the client expects when receiving a result set. The server converts string data in results, metadata, and error messages according to this setting before sending them back to the client.

Example:

~~~sql
SELECT customer_id, full_name
FROM customers
ORDER BY customer_id;
~~~

If the full_name column uses utf8mb4 while the session's character_set_results is a character set unable to represent certain characters in the data, converting the results can fail or fail to preserve content as intended.

### 5.2. Checking

~~~sql
SELECT @@SESSION.character_set_results;
~~~

Or:

~~~sql
SHOW SESSION VARIABLES LIKE 'character_set_results';
~~~

A NULL value has a special meaning: the server performs no character set conversion step for results. In that case, the client must understand and decode the sent bytes according to the actual encoding supplied by the server.

Do not set NULL unless the application or client protocol knows exactly how to process unconverted results. For typical applications, letting the connector manage an appropriate character_set_results is safer and easier to maintain.

### 5.3. Results include more than column values

character_set_results also relates to how the server sends metadata and error messages containing string text. Therefore, when encountering display corruption in both data and server messages, inspect the result transmission pipeline rather than only the table's charset.

## 6. Setting all three variables with SET NAMES

### 6.1. Syntax

SET NAMES is a convenient way to set the session's primary character set variables:

~~~sql
SET NAMES utf8mb4;
~~~

This statement is equivalent in intent to setting:

~~~sql
SET character_set_client = utf8mb4;
SET character_set_connection = utf8mb4;
SET character_set_results = utf8mb4;
~~~

When executing SET NAMES, MySQL also sets collation_connection to the character set's default collation if COLLATE is not specified. You can specify a collation explicitly:

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

This statement also sets collation_connection to the chosen collation.

### 6.2. Scope of effect

SET NAMES changes the configuration of the current session. It does not automatically alter the default character set and collation of databases, tables, or columns. Nor does it convert data already stored in tables.

If you run SET NAMES on one connection, other connections are unaffected. When the connection closes, that session change does not become a persistent server default.

### 6.3. Why should you not change only one variable?

If you change only character_set_client without changing character_set_connection and character_set_results, the string pipeline becomes inconsistent. The client sends one encoding, the server interprets literals in another encoding, and returns results in a third encoding.

SET NAMES helps configure all three variables consistently to the same character set. However, when using a modern connector, prefer configuring the charset through the driver's API or connection properties. Some drivers maintain their own encoding state; sending SET NAMES manually can cause client and server state to diverge if the driver is unaware of the change.

## 7. Distinguishing SET NAMES and SET CHARACTER SET

These two statements behave differently:

| Statement | character_set_client | character_set_connection | character_set_results | collation_connection |
|---|---|---|---|---|
| SET NAMES utf8mb4 | utf8mb4 | utf8mb4 | utf8mb4 | Default collation of utf8mb4 |
| SET CHARACTER SET utf8mb4 | utf8mb4 | Default character set of the current database (or server if no default database) | utf8mb4 | Corresponding default collation of the database (or server) |

SET CHARACTER SET sets character_set_client and character_set_results to the specified character set, while setting character_set_connection and collation_connection to the defaults of the current database. If no database is selected, the server defaults are used.

Example:

~~~sql
USE shop;
SET CHARACTER SET utf8mb4;

SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.collation_connection;
~~~

If the database has a different default character set or collation than expected, character_set_connection after SET CHARACTER SET may not be utf8mb4. When the goal is to set all three variables to utf8mb4, SET NAMES is usually clearer.

## 8. Distinguishing connection charset from database, table, and column charsets

The three variables covered here control a client session's communication. They do not replace schema-level charset settings.

MySQL has other configuration scopes:

| Scope | Variable or metadata | Meaning |
|---|---|---|
| Server | character_set_server, collation_server | Default values at the server level |
| Database | DEFAULT CHARACTER SET, DEFAULT COLLATE | Default values for new objects in the database |
| Table | DEFAULT CHARSET, COLLATE in DDL | Default values for new string columns in the table |
| Column | Column CHARACTER SET, COLLATE | How strings in that column are stored and compared |
| Connection | character_set_client, character_set_connection, character_set_results | How statements are interpreted, literals processed, and results returned for a session |

Example of viewing database settings:

~~~sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = 'shop';
~~~

Viewing column charset and collation:

~~~sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND CHARACTER_SET_NAME IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
~~~

Setting the default charset for a new database:

~~~sql
CREATE DATABASE shop_utf8
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Setting the default charset for a table:

~~~sql
CREATE TABLE notes (
    note_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    body TEXT NOT NULL,
    PRIMARY KEY (note_id)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

If a column already has its own character set, changing the connection charset does not automatically change the column's charset. Conversely, changing the table's charset does not automatically guarantee the application sends and receives bytes in the right encoding.

## 9. Practical examples with Vietnamese data and emojis

### 9.1. Checking session configuration

Connect to MySQL and run:

~~~sql
SELECT
    @@SESSION.character_set_client AS client_charset,
    @@SESSION.character_set_connection AS connection_charset,
    @@SESSION.character_set_results AS results_charset,
    @@SESSION.collation_connection AS connection_collation;
~~~

For a modern Unicode application, the desired configuration is typically utf8mb4 for all three variables and a collation matching the string comparison requirements.

### 9.2. Testing passing literals

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;

SELECT
    'Tiếng Việt có dấu' AS vietnamese_text,
    '🙂' AS emoji_text,
    CHARSET('Tiếng Việt có dấu') AS literal_charset,
    COLLATION('Tiếng Việt có dấu') AS literal_collation;
~~~

If the terminal or SQL tool displays text incorrectly, identify which layer has the issue: terminal, driver, character_set_client, character_set_connection, character_set_results, or font. Not every display bug originates in MySQL.

### 9.3. Testing writing and reading

~~~sql
CREATE TABLE IF NOT EXISTS charset_demo (
    demo_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    message VARCHAR(200) NOT NULL,
    PRIMARY KEY (demo_id)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;

INSERT INTO charset_demo (message)
VALUES ('Xin chào Việt Nam 🙂');

SELECT demo_id, message
FROM charset_demo
ORDER BY demo_id DESC
LIMIT 1;
~~~

This test should only be run on a test database or a table permitted for experimentation. When storing production data, use migrations and the project's schema management workflow.

## 10. Examples of errors due to inconsistent charsets

Suppose the application encodes strings in UTF-8, yet the connection declares character_set_client as latin1. UTF-8 bytes can be interpreted as separate latin1 characters. Depending on the string and conversion steps, the result can become mojibake or raise an error when converting to character_set_connection.

Another case: client and server communicate properly in UTF-8 and data is stored accurately in a utf8mb4 column, yet character_set_results is set to a character set incapable of representing certain characters. When the server converts results, data can be corrupted or fail to return intact.

Conversely, if the server sends UTF-8 bytes yet the application decodes them as Windows-1252 or latin1, users still see wrong characters even though the data in the database is completely valid.

Investigation steps:

1. Check the encoding the application actually uses to encode requests.
2. Check character_set_client, character_set_connection, and character_set_results of the exact session.
3. Check the character set and collation of the database, table, and column.
4. Determine whether data goes wrong when sent, when stored, or only when read and displayed.
5. Use test data containing Vietnamese text, non-BMP characters, and emojis to reproduce.
6. Fix the configuration at the right layer, then test INSERT, SELECT, comparisons, and sorting.

Do not attempt to fix mojibake data by randomly changing the connection charset. First determine what raw bytes are currently stored and which layer misinterpreted them; otherwise, conversion operations can further corrupt the data.

## 11. How to configure in applications

### 11.1. Let the connector manage the connection

For JDBC, Python, .NET, PHP, or Node.js, configure encoding and collation using the connector's official options. The driver can set the charset during the handshake, issue session commands, or manage client-side encoding/decoding.

There is no single configuration property name shared across all drivers. Consult the documentation for the exact connector and version you deploy. After connecting, verify with the query:

~~~sql
SELECT
    @@SESSION.character_set_client,
    @@SESSION.character_set_connection,
    @@SESSION.character_set_results,
    @@SESSION.collation_connection;
~~~

If the application uses a connection pool, ensure every physical connection in the pool is created with consistent settings. Also watch out for modifying session state on a connection before returning it to the pool: the state may persist for the next request if the pool does not reset the session.

### 11.2. When using SET NAMES manually

In test environments or command-line clients, you can use:

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

In applications where a driver manages the charset, avoid sending this statement arbitrarily after the driver has initialized the connection. If the driver is not informed of the session change, client-side encoding/decoding may diverge from server settings.

### 11.3. Checking after acquiring a connection from a pool

When an application borrows a connection from a pool, rely on pool/driver configuration and supported connection-reset mechanisms. If code changes a session variable, restore the initial state before returning the connection or configure the pool to reset session state appropriately. This prevents one request from affecting another.

## 12. Common misconceptions

**"character_set_client is the column's charset."** No. It describes the encoding MySQL uses to interpret statement bytes from the client.

**"character_set_connection determines the charset of the entire table."** No. It controls the default character set for literals and string processing in the session; column charsets are defined separately.

**"character_set_results determines how MySQL stores data."** No. It controls conversion of results sent back to the client.

**"SET NAMES changes the database's charset."** No. SET NAMES changes connection session variables.

**"utf8 in MySQL is always full UTF-8."** In MySQL, the name utf8 is historically an alias for utf8mb3 in modern versions; utf8mb3 supports at most three bytes per character. Use utf8mb4 when full Unicode is needed, including emojis and non-BMP characters.

**"Changing the connection charset fixes data that was already stored incorrectly."** No. It only changes how data is interpreted or converted within the session. Fixing improperly stored data requires identifying the existing byte encoding and planning a separate data conversion.

**"If MySQL returns a corrupted string, the database must have stored it wrong."** No. The bug can lie in request encoding, session settings, result conversion, the driver, the terminal, or fonts.

## 13. Checklist for troubleshooting Vietnamese text errors

When encountering broken Vietnamese diacritics, special characters, or emojis, check in order:

1. The application constructs valid Unicode strings before calling the driver.
2. The connector is configured to send and receive UTF-8/utf8mb4.
3. character_set_client matches the byte encoding sent by the client.
4. character_set_connection and collation_connection match how literals should be processed.
5. character_set_results matches the encoding decoded by the client.
6. The database, table, and column have a character set capable of representing the data.
7. The column's collation matches search, comparison, and sorting rules.
8. The connection pool does not retain stale session state from a prior request.
9. Run a round-trip test: write the string, read it back, and compare it strictly with the original string.

A useful summary query:

~~~sql
SELECT
    @@SESSION.character_set_client AS character_set_client,
    @@SESSION.character_set_connection AS character_set_connection,
    @@SESSION.character_set_results AS character_set_results,
    @@SESSION.collation_connection AS collation_connection,
    @@GLOBAL.character_set_server AS character_set_server,
    @@GLOBAL.collation_server AS collation_server;
~~~

This query helps distinguish session configuration from server defaults. To verify column charsets, query INFORMATION_SCHEMA.COLUMNS as shown in the earlier example.

## Conclusion

character_set_client tells MySQL the byte encoding of statements received from the client; character_set_connection determines the default character set and collation used when processing literals; character_set_results determines how the server converts data, metadata, and messages returned to the client. Together, these three variables form a continuous pipeline from request to response.

For modern applications, use utf8mb4 consistently across connectors and columns storing Unicode, choose collations according to comparison requirements, and verify actual session settings. When text displays incorrectly, pinpoint the exact layer where the error occurs before attempting any data conversion or repair. This approach preserves Vietnamese text, emojis, and multilingual data in MySQL applications.
