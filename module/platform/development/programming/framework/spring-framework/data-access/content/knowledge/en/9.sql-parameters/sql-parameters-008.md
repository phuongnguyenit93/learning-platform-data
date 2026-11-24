# The LIKE Operator, Wildcards, and Search Policies in Spring JDBC

## 1. The Problem: Users Type Text, While SQL Interprets Patterns

Suppose a customer search box receives `Lan`, `Lan_Pro`, `50%`, or `O'Reilly`. A system may require exact matching, prefix matching, substring matching, or allow advanced patterns. Each policy leads to a query with different semantics and performance.

SQL's `LIKE` operator uses a **pattern**; the characters `%` and `_` are wildcards. Therefore, a keyword `50%` typed by a user intending to find a literal percent sign can cause the query to match `50 Percent` if the application does not handle it properly.

This lesson distinguishes:

1. **SQL syntax:** `LIKE`, the two wildcards, `ESCAPE`, `NULL`, and collation.
2. **How values are passed:** `JdbcTemplate` or `NamedParameterJdbcTemplate` uses parameters to prevent SQL injection.
3. **Product policies:** exact/prefix/contains, literal vs. pattern keywords, case sensitivity, Vietnamese diacritics, empty input, result limits, and performance.

**Safe, predictable rule:** treat user-entered content as **literal by default**. The application actively adds wildcards for a specific feature; never implicitly allow users to control wildcards merely because they typed `%` or `_`.

## 2. How Do `LIKE`, `%`, and `_` Differ?

```sql
SELECT id, display_name
FROM customers
WHERE display_name LIKE 'Lan%'
ORDER BY id;
```

| Symbol | Meaning in LIKE | Example |
| --- | --- | --- |
| `%` | Zero or more characters | `'Lan%'` matches `Lan` and `Lan Anh` |
| `_` | Exactly one character as defined by the DB | `'Lan_'` matches `Lany`, not `Lan Anh` |
| Other characters | Ordinary characters, subject to collation | `'Lan'` is a pattern without wildcards |
| `ESCAPE` | Specifies how to use wildcards literally | `'50!%' ESCAPE '!'` matches the text `50%` |

Common forms:

```sql
-- Exact match (per DB comparison rules):
WHERE display_name = 'Lan'

-- Names starting with "Lan":
WHERE display_name LIKE 'Lan%'

-- Names ending with "Lan":
WHERE display_name LIKE '%Lan'

-- Names containing "Lan":
WHERE display_name LIKE '%Lan%'

-- Names consisting of "Lan" followed by exactly one character:
WHERE display_name LIKE 'Lan_'
```

`%` can represent **0 characters**, so `'Lan%'` also matches the name `Lan`. `_` requires exactly one character per DB rules, so `'Lan_'` does not match `Lan`. For multi-code-point Unicode strings, one visible user character may not correspond to one DB counting unit; test against the real dialect/collation.

`LIKE` is not regex. `*` and `?` are not the two standard `LIKE` wildcards; regex/`SIMILAR TO`/full-text search syntax are different features. Do not apply Java regex rules to SQL `LIKE`.

### 2.1. Collation Governs Character Comparison

Some DBMSs or collations treat `Lan` and `lan` as equal; other configurations distinguish them. Even `=` and `LIKE` can be affected by collation, `CHAR` types, Unicode characters, and trailing spaces. Do not assume H2 results match PostgreSQL/MySQL/SQL Server identically.

## 3. Using `ESCAPE '!'` to Search for Literal Wildcards

For example, the user wants to find the **percent sign** in `50%`, not "every string starting with 50":

```sql
SELECT display_name
FROM customers
WHERE display_name LIKE '%50!%%' ESCAPE '!';
```

Explaining the pattern `%50!%%`:

- Leading `%`: any prefix;
- `50`: digits `5`, `0`;
- `!%`: **literal** percent sign;
- Trailing `%`: any suffix.

Then `50% Sale` matches, while `50 Percent` does not. Similarly:

```sql
-- Strings containing exact "Lan_" (with a real underscore):
WHERE display_name LIKE '%Lan!_%' ESCAPE '!'

-- Strings containing exact "Lan!" (with a real exclamation mark):
WHERE display_name LIKE '%Lan!!%' ESCAPE '!'
```

If you choose `!` as the escape character, you must escape **`!` itself** in the input too. The table below shows **value strings to bind into SQL**, not SQL segments assembled via string concatenation:

| User Keyword | After Escaping | Pattern Containing Literal |
| --- | --- | --- |
| `Lan` | `Lan` | `%Lan%` |
| `50%` | `50!%` | `%50!%%` |
| `Lan_` | `Lan!_` | `%Lan!_%` |
| `Lan!` | `Lan!!` | `%Lan!!%` |
| `50%_!` | `50!%!_!!` | `%50!%!_!!%` |
| `O'Reilly` | `O'Reilly` | `%O'Reilly%` |

Java helper:

```java
static String escapeLikeLiteral(String input) {
    return input
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
```

**Order is part of the algorithm.** You must double `!` before prefixing `!` to `%` and `_`. If you double `!` last, the newly added escape markers will be altered, producing a broken pattern.

Specifying an explicit escape character avoids relying on a default backslash, because backslashes can interact with Java/SQL string escaping rules and differ across DBs. `ESCAPE '!'` syntax is supported by H2, though when switching RDBMSs you still need to check syntax, collation, and dedicated unit/integration tests.

## 4. Why Is Parameter Binding Still Not Enough for Literal LIKE?

The following query uses parameter binding:

```java
String pattern = "%" + userInput + "%";
List<String> names = jdbc.query(
        "SELECT display_name FROM customers " +
        "WHERE display_name LIKE ? ORDER BY id",
        (rs, rowNum) -> rs.getString(1),
        pattern);
```

It resists SQL injection because it does not insert input as SQL syntax. However, if `userInput = "%"`, the pattern becomes `"%%%"`: the wildcard matches nearly every non-`NULL` string value. The user has controlled **the match scope**, even without interfering with the SQL parser.

Separate the two layers:

- **Parameter binding:** passes `?`/`:name` as data; the `'` in `O'Reilly` does not close an SQL literal; the string `' OR 1=1 --` does not become SQL logic.
- **LIKE escaping:** turns user-entered special characters into literals. Under a literal-contains policy, only the application may intentionally add leading/trailing `%`.

Safe pattern:

```java
String pattern = "%" + escapeLikeLiteral(userInput) + "%";
List<String> names = jdbc.query(
        "SELECT display_name FROM customers " +
        "WHERE display_name LIKE ? ESCAPE '!' ORDER BY id",
        (rs, rowNum) -> rs.getString(1),
        pattern);
```

Both snippets above assume `jdbc` already exists and input is validated; they are **not standalone runnable Java files**. Using `userInput` directly to concatenate SQL is dangerous:

```java
// WRONG: user data becomes SQL syntax.
String sql = "SELECT * FROM customers WHERE display_name LIKE '%"
        + userInput + "%'";
jdbc.queryForList(sql);
```

If the user enters a single quote or malicious SQL payload, the query can break or suffer SQL injection. Do not manually replace `'` with `''` in Java when already binding values; that is for literals in SQL text, not the responsibility of bound data.

## 5. Search Policies: EXACT, PREFIX, SUFFIX, CONTAINS

API design should state intent explicitly rather than letting the service guess client patterns:

| Mode | SQL | Parameter |
| --- | --- | --- |
| EXACT | `column = ?` | Literal string (no LIKE needed) |
| PREFIX | `column LIKE ? ESCAPE '!'` | `escaped + "%"` |
| SUFFIX | `column LIKE ? ESCAPE '!'` | `"%" + escaped` |
| CONTAINS | `column LIKE ? ESCAPE '!'` | `"%" + escaped + "%"` |
| ADVANCED | `column LIKE ? ESCAPE '!'` | Pattern per a clearly published grammar |

For a general search box, users should pick **starts with** or **contains** in the UI. The server accepts a validated enum and builds the pattern itself. Avoid "user typing `%` means wildcard" when the interface never explains that behavior.

### 5.1. Policies for `null`, Empty, and Whitespace

The application must decide what happens when input is `null`, `""`, or whitespace-only:

1. Return a validation error if the search box requires content.
2. Return an empty list without calling the DB.
3. Switch to browse mode with pagination, sorting, and authorization.

Never silently turn it into `LIKE '%%'`. In most DBs, that pattern matches broadly across all non-NULL strings, slowing down the query and potentially returning unintended data.

Trim rules must also be clear: `"  Lan  "` becomes `"Lan"` with Java `strip()`, whereas for product codes where leading/trailing spaces are significant, trimming should not occur. Maximum/minimum lengths depend on UI and data scale; there is no single constant right for every system.

### 5.2. Never Let Clients Inject Column Names or ORDER BY

`?` only binds **values**, not column/table names or `ASC`/`DESC` keywords. If users choose "Search by name or email," the server must use an allowlist:

```java
// Illustrative snippet: field is a server-validated enum.
String column = switch (field) {
    case NAME -> "display_name";
    case EMAIL -> "email";
};

String sql = "SELECT id FROM customers WHERE " +
        column + " LIKE ? ESCAPE '!' ORDER BY id";
```

This chooses between **two fixed SQL strings owned by the application**, never concatenating any client content into an identifier.

## 6. Complete Java 17+ Program: Spring JDBC with H2

The following example pins Java 17+, Spring Framework 6.2.12, and H2 2.3.232 for reproducibility. No Spring Boot or external database server installation is needed.

It creates a DAO using `JdbcTemplate` and a stateless `RowMapper<String>`; it uses H2 `LIKE ? ESCAPE '!'` and server-constructed patterns.

### 6.1. File Structure and Maven

```text
like-policy-demo/
├── pom.xml
└── src/main/java/example/LikePolicyDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>like-policy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/LikePolicyDemo.java`:

```java
package example;

import java.util.List;
import java.util.Locale;
import java.util.Objects;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class LikePolicyDemo {
    enum Mode { EXACT, PREFIX, CONTAINS }

    static final class SearchDao {
        private static final RowMapper<String> NAME_MAPPER =
                (rs, rowNum) -> rs.getString("display_name");

        private final JdbcTemplate jdbc;

        SearchDao(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private static String validate(String input) {
            if (input == null) {
                throw new IllegalArgumentException("Search input is null");
            }
            String text = input.strip();
            if (text.isBlank() || text.length() > 60) {
                throw new IllegalArgumentException("Invalid search length");
            }
            return text;
        }

        private static String escapeLike(String literal) {
            return literal
                    .replace("!", "!!")
                    .replace("%", "!%")
                    .replace("_", "!_");
        }

        List<String> search(String input, Mode mode) {
            Objects.requireNonNull(mode, "mode");
            String text = validate(input);
            String escaped = escapeLike(text);
            String operator = mode == Mode.EXACT
                    ? "= ?" : "LIKE ? ESCAPE '!'";

            String parameter = switch (mode) {
                case EXACT -> text;
                case PREFIX -> escaped + "%";
                case CONTAINS -> "%" + escaped + "%";
            };

            return jdbc.query(
                    "SELECT display_name FROM customers WHERE display_name " +
                    operator + " ORDER BY id",
                    NAME_MAPPER,
                    parameter);
        }

        List<String> containsIgnoreCase(String input) {
            String text = validate(input);
            String pattern = "%" +
                    escapeLike(text.toLowerCase(Locale.ROOT)) + "%";

            return jdbc.query(
                    "SELECT display_name FROM customers " +
                    "WHERE LOWER(display_name) LIKE ? ESCAPE '!' ORDER BY id",
                    NAME_MAPPER,
                    pattern);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:likepolicy;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource source) {
            return new JdbcTemplate(source);
        }

        @Bean
        SearchDao searchDao(JdbcTemplate jdbc) {
            return new SearchDao(jdbc);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            SearchDao dao = context.getBean(SearchDao.class);

            jdbc.execute(
                    "CREATE TABLE customers (" +
                    "id BIGINT PRIMARY KEY, display_name VARCHAR(100) NOT NULL)");

            String insert =
                    "INSERT INTO customers (id, display_name) VALUES (?, ?)";
            jdbc.update(insert, 1L, "Lan Anh");
            jdbc.update(insert, 2L, "Lan_Pro");
            jdbc.update(insert, 3L, "Nam");
            jdbc.update(insert, 4L, "50% Sale");
            jdbc.update(insert, 5L, "50 Percent");
            jdbc.update(insert, 6L, "ALAN");
            jdbc.update(insert, 7L, "Lan! VIP");
            jdbc.update(insert, 8L, "Lan% VIP");
            jdbc.update(insert, 9L, "Lany");
            jdbc.update(insert, 10L, "lan junior");
            jdbc.update(insert, 11L, "O'Reilly");

            System.out.println("Exact: " +
                    dao.search("Lan Anh", Mode.EXACT));
            System.out.println("Prefix: " +
                    dao.search("Lan", Mode.PREFIX));
            System.out.println("Literal underscore: " +
                    dao.search("Lan_", Mode.CONTAINS));
            System.out.println("Literal percent: " +
                    dao.search("50%", Mode.CONTAINS));
            System.out.println("Literal escape: " +
                    dao.search("Lan!", Mode.CONTAINS));
            System.out.println("Apostrophe: " +
                    dao.search("O'Reilly", Mode.CONTAINS));
            System.out.println("Case insensitive: " +
                    dao.containsIgnoreCase("lan"));
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.LikePolicyDemo
```

Lines printed by the program with configured H2 (ignoring Maven logs that may appear depending on environment):

```text
Exact: [Lan Anh]
Prefix: [Lan Anh, Lan_Pro, Lan! VIP, Lan% VIP, Lany]
Literal underscore: [Lan_Pro]
Literal percent: [50% Sale]
Literal escape: [Lan! VIP]
Apostrophe: [O'Reilly]
Case insensitive: [Lan Anh, Lan_Pro, ALAN, Lan! VIP, Lan% VIP, Lany, lan junior]
```

### 6.2. Why Do the Output Lines Differ?

- `Exact` uses `= ?` with `Lan Anh`, without wildcards.
- `Prefix` uses pattern `Lan%`, returning names starting with `Lan` in the example's case-sensitive H2 database.
- `Literal underscore` turns `Lan_` into `%Lan!_%`, so only the name containing an actual underscore matches.
- `Literal percent` turns `50%` into `%50!%%`, without returning `50 Percent`.
- `Literal escape` turns `Lan!` into `%Lan!!%`, preserving the exact `!` character.
- `Apostrophe` uses parameter binding, so `O'Reilly` does not break the SQL.
- `Case insensitive` combines `LOWER(display_name)` and `Locale.ROOT` for unaccented Latin strings in demo data. It **does not** automatically handle accent-insensitive search or complex Unicode case folding in production.

`strip()` and the 60-character limit are illustrative policies, not Spring defaults. `DriverManagerDataSource` is used for the lesson without a connection pool; real applications typically need HikariCP or another pool. H2 option `DB_CLOSE_DELAY=-1` keeps the in-memory database alive across the demo's connections.

### 6.3. The Tools Do Not Inspect User Intent Automatically

`JdbcTemplate` prepares statements and manages JDBC resources. `RowMapper` creates Java objects from each row. Neither **knows automatically** whether the user wants literal, prefix, or advanced wildcard search. The DAO/service itself must define the search policy and transform the pattern.

## 7. What About NamedParameterJdbcTemplate?

`NamedParameterJdbcTemplate` allows named parameters like `:pattern`, which are easier to read when there are many conditions, yet **does not change** `LIKE` semantics:

```java
// Snippet: assumes namedJdbc, Map, validate, and escapeLike are defined.
String pattern = "%" + escapeLike(userText) + "%";
List<String> results = namedJdbc.query(
        "SELECT display_name FROM customers " +
        "WHERE display_name LIKE :pattern ESCAPE '!' ORDER BY id",
        Map.of("pattern", pattern),
        (rs, rowNum) -> rs.getString("display_name"));
```

The `:pattern` name is Spring's parameter binding mechanism; `%` characters inside the value remain SQL wildcards unless escaped. Other values like `:tenantId` or `:status` are also bound; table/column/sort names must be chosen from an application allowlist, not concatenated from requests.

## 8. Hard Cases: Letter Case, Vietnamese Diacritics, and Unicode

For Vietnamese-language products, a requirement like "case-insensitive and accent-insensitive" must be written into explicit rules:

- Are `Lan` and `lan` equivalent?
- Are `Hoa` and `Hòa` equivalent?
- Are `đ` and `d` equivalent?
- Should composed and decomposed Unicode representations match?
- Should leading/trailing spaces be stripped and internal spaces normalized?

`LOWER(name) LIKE ?` can handle simple case-insensitivity, yet **does not** strip Vietnamese diacritics. Java's `toLowerCase(Locale.ROOT)` also does not guarantee exact parity with the database's comparison algorithm. You need an appropriate collation, consistent normalization, or a controlled normalized search column.

Some DBs offer `ILIKE` (such as PostgreSQL, H2), though it is not portable SQL across all RDBMSs. `ILIKE` also still has `%` and `_` wildcards, so literal input escaping is still needed. Do not use `ILIKE` and forget user search policies.

### 8.1. Nullable Columns and Three-Valued Logic

`NULL` is not the same as an empty string. In SQL:

```sql
SELECT id FROM customers
WHERE display_name LIKE '%Lan%';

SELECT id FROM customers
WHERE display_name NOT LIKE '%Lan%';
```

If `display_name IS NULL`, both `LIKE` and `NOT LIKE` evaluate to UNKNOWN rather than TRUE. `WHERE` will not return NULL rows. If policy requires treating NULL as "not matching," write it explicitly:

```sql
SELECT id FROM customers
WHERE display_name IS NULL
   OR display_name NOT LIKE '%Lan%';
```

Do not arbitrarily use `COALESCE(display_name, '')` because it alters semantics and can affect indexes. The demo table has no NULLs to stay focused on wildcards, yet production queries must consider schema and `LEFT JOIN` results.

## 9. Performance of `'prefix%'` vs. `'%contains%'`

Even with the same literal string, search mode strongly affects B-tree index usability.

| Pattern | Purpose | Typical Index Usability |
| --- | --- | --- |
| `column = ?` | Exact | Usually favorable |
| `column LIKE 'Lan%'` | Prefix | Can optimize via range scan, depending on collation/operator |
| `column LIKE '%Lan'` | Suffix | Leading wildcard usually prevents prefix scan |
| `column LIKE '%Lan%'` | Contains | Easily scans many rows without specialized index |
| `LOWER(column) LIKE 'lan%'` | Case-insensitive | May need an expression index or collation index |

These are **tendencies**, not planner guarantees: H2, PostgreSQL, MySQL/SQL Server have different engines, collations, statistics, and indexing strategies. Inspect `EXPLAIN` or execution plans on realistically sized data.

If the UI is autocomplete, prefix search can both fit UX and reduce load. If the product genuinely needs substring search across millions of rows, consider `pg_trgm` (PostgreSQL), full-text indexes, or a dedicated search engine, along with benchmarks and semantics testing. Do not use `'%term%'` on every screen just because it "easily returns more matches."

### 9.1. Result Limits and Access Control

- Enforce **server-side** limits/pagination, not only limiting items displayed on the client.
- Use stable `ORDER BY` with `id` as a tie-breaker when paging.
- Filter by tenant/ownership/role; escaping does not replace authorization.
- Apply query timeouts/rate limiting/debouncing for search requests triggered as users type.
- Avoid `SELECT *`; select only columns needed for display.
- Test against a production database; measure scanned rows, query duration, and connection pool usage.

The following SQL works on H2/PostgreSQL, though limit/offset is **not portable to every dialect**:

```sql
SELECT id, display_name
FROM customers
WHERE tenant_id = ?
  AND display_name LIKE ? ESCAPE '!'
ORDER BY display_name, id
LIMIT ? OFFSET ?;
```

The `?` markers must be bound in order: tenant, pattern, limit, offset; all must be validated. On SQL Server/Oracle or other dialects, use their respective pagination syntax. Queries with leading wildcards can still be costly even when row count is limited.

## 10. When Should Users Be Allowed to Type Wildcards?

Some internal tools intentionally offer "pattern search." Design it as an explicit mode:

1. Show guidance that `%` matches zero or more characters and `_` matches one character.
2. Document how to write literal `%` and `_` using `!` escaping, or provide a UI separating wildcards from literals.
3. Validate length, wildcard count, overly broad patterns, and access permissions.
4. Bind the entire allowed pattern via parameters; **never** concatenate user SQL syntax.
5. Limit result count, query timeout, and log safely without arbitrarily logging sensitive data.
6. Test with patterns ending in the escape character and diverse Unicode strings.

For most products, an `Exact / Starts with / Contains` dropdown is friendlier and easier to control than exposing raw SQL syntax in the UI.

## 11. Testing: Do Not Just Assert the Query Returns One Result

Datasets must have **positive and negative** cases for every special character:

| Keyword and Mode | Must Include | Must Exclude |
| --- | --- | --- |
| `50%` CONTAINS literal | `50% Sale` | `50 Percent` |
| `Lan_` CONTAINS literal | `Lan_Pro` | `Lany` |
| `Lan!` CONTAINS literal | `Lan! VIP` | `Lan Anh` |
| `%` CONTAINS literal | Names actually containing `%` | Every name without `%` |
| `O'Reilly` CONTAINS literal | `O'Reilly` | SQL syntax error |
| `Lan` PREFIX | Names starting with `Lan` | `ALAN` in case-sensitive setup |
| `null`, `""`, whitespace | Validation behavior per policy | Turning silently into `LIKE '%%'` |

Also test strings containing `!!`, `!%`, `!_`, accented Unicode characters, required case/accent rules, SQL NULL columns, overly long inputs, and concurrent requests.

Illustrative JUnit 5 test for the escape helper (snippet needs corresponding dependencies/imports, **not included in section 6's Maven project**):

```java
@Test
void escapesWildcardAndEscapeCharacter() {
    assertEquals("50!%!_!!", escapeLikeLiteral("50%_!"));
    assertEquals("!!", escapeLikeLiteral("!"));
    assertEquals("!_", escapeLikeLiteral("_"));
}
```

String unit tests only verify the Java algorithm. **Integration tests** with the right JDBC driver/DB are what verify `ESCAPE '!'`, collation, Unicode, and query results. When production uses PostgreSQL/MySQL/SQL Server, test on that database rather than relying solely on H2.

## 12. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Concatenating `userInput` directly into SQL | SQL injection, apostrophe errors | Bind via `?`/`:name` |
| Binding `LIKE ?` without escaping literals | Input `%`/`_` alters match scope | Escape both wildcards and marker |
| Escaping `!` last | Doubles newly added markers, breaking pattern | Escape `!` before `%` and `_` |
| Forgetting `ESCAPE '!'` | DB may misinterpret `!%` | Keep SQL and escape helper aligned |
| Turning empty input into `LIKE '%%'` | Overly broad results, expensive query | Define reject/empty/browse policy |
| Treating `LOWER` as accent-insensitive | Wrong Vietnamese search semantics | Collation/normalization and tests |
| Using contains for massive autocomplete | Index is hard to optimize | Prefix or text search index |
| Assuming `NOT LIKE` includes SQL NULL | NULL records missing from results | Add `IS NULL` if policy requires |
| Paginating without sorting | Duplicate/missing results | Stable `ORDER BY` |
| No result limits | DB, network, and heap overload | Limits, paging, timeouts, rate limits |
| Concatenating column/sort names from request | Identifier injection | Enum/allowlist |
| Assuming every DB acts like H2 | Wrong collation/escape/index behavior | Integration tests on real dialect |

## 13. Practical Workflow for Designing a Search API

1. **Define search contract:** EXACT/PREFIX/CONTAINS, literal vs. pattern, case/diacritics.
2. **Validate server-side:** blank, null, length, whitespace, bounds, and access control.
3. **Escape literals:** `!` then `%` and `_`; add wildcards for the chosen mode.
4. **Bind parameters:** use `JdbcTemplate` or `NamedParameterJdbcTemplate`, never concatenate input into SQL.
5. **Keep SQL structure fixed:** column/sort names from allowlist, never arbitrary expressions.
6. **Declare ESCAPE explicitly:** keep consistent with Java helper and test special characters.
7. **Set limit/ORDER BY/paging:** avoid unbounded queries.
8. **Test end-to-end:** positive/negative wildcards, apostrophes, null, Unicode, dialect.
9. **Measure cost:** indexes, EXPLAIN, query duration, pool, and load capacity.

### Self-Check Questions

1. Why does `'Lan%'` match `Lan`, whereas `'Lan_'` does not?
2. If `LIKE ?` receives the pattern `"%"`, does the query suffer from SQL injection? Can it still return too much data?
3. What pattern must be passed to search for substring containing literal `50%_!` with `ESCAPE '!'`?
4. Why must the escape marker `!` be escaped before handling `%` and `_`?
5. Why does binding `O'Reilly` with `?` not require manually handling single quotes?
6. Does `NULL NOT LIKE '%Lan%'` include NULL rows in `WHERE`?
7. Why is `'%Lan%'` usually more expensive than `'Lan%'` with a B-tree?
8. Is `LOWER(name)` enough for accent-insensitive Vietnamese search?
9. Can an `ORDER BY` column name be bound with `?`?
10. Beyond escaping, what policies are needed to prevent returning overly broad or unauthorized data?

**Conclusion:** `LIKE` uses `%` and `_` as wildcards. For normal search boxes, input must be treated as **literal by default**; escape `%`, `_`, and the escape marker with an explicit `ESCAPE` clause, then add wildcards solely according to application-chosen modes. Spring `JdbcTemplate` protects SQL syntax via binding, while correctness also depends on search policy, collation/Unicode, SQL NULL, pagination, authorization, and performance measurement.

### Official References

- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JdbcTemplate JavaDoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — Named Parameters: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- H2 Database — LIKE and ESCAPE: https://h2database.github.io/html/grammar.html
- PostgreSQL — Pattern Matching: https://www.postgresql.org/docs/current/functions-matching.html
