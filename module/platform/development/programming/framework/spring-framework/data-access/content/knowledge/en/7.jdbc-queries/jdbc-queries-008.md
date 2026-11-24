# Designing Optional or Empty Results in Repository Contracts

In the **JDBC query** layer of Spring Framework, a SELECT statement can return **0 rows**, **1 row**, or **multiple rows**. How a repository advertises that result is part of its API contract: callers must know when **not found** is a valid outcome, when **a missing record** is a business error, and when the database or data has violated an assumption.

A good contract communicates this directly in its return type:

- **Optional<T>**: **0 or 1** object; absence is an expected outcome.
- **List<T>**: **0 to many** objects; zero elements is an **empty list**.
- **Required T**: **exactly 1** object; absence or more than one must have a defined handling policy.
- **boolean**: answers whether something exists.
- **long/int**: represents a count, including 0.

This lesson focuses on Spring JDBC's JdbcTemplate, NamedParameterJdbcTemplate, JdbcClient, and DataAccessUtils with Java 17+; SQL examples use H2/PostgreSQL. It also distinguishes **SQL returning no rows**, **one row with a NULL column**, **multiple-row errors**, **database access errors**, and how services consume results.

## 1. Define the Cardinality Contract Before Choosing an API

**Cardinality** is the number of records a query may return per business rules. A method's contract should specify at least four things: inputs, valid result counts, value when there is no data, and behavior when data violates constraints.

| Business method | Cardinality | Suggested signature | On 0 rows |
| --- | --- | --- | --- |
| Find one user by primary key | 0..1 | Optional<User> findById(long id) | Optional.empty() |
| Find user by UNIQUE email | 0..1 | Optional<User> findByEmail(String email) | Optional.empty() |
| Find all users by status | 0..n | List<User> findByStatus(String status) | Empty list |
| Read required user for a command | Exactly 1 | User getRequiredById(long id) | Intentional error |
| Check if ID exists | true/false | boolean existsById(long id) | false |
| Count users by status | A count | long countByStatus(String status) | 0 |
| Paginated query | 0..n + metadata | PageResult<User> | Empty items with page metadata |

Example signatures:

~~~java
import java.util.List;
import java.util.Optional;

public interface UserRepository {
    Optional<User> findById(long id);
    Optional<User> findByEmail(String email);
    List<User> findByStatus(String status);
    User getRequiredById(long id);
    boolean existsById(long id);
    long countByStatus(String status);
}
~~~

This is a **design illustration**; the User domain type must be defined by the application. Do not represent the same "not found" concept inconsistently—returning null in one place, Optional.empty() in another, and an empty List arbitrarily elsewhere. Conventions must flow from each method's cardinality.

**Method names are also contracts:** findById hints that absence is allowed; getRequiredById signals it must exist; findAllByStatus clearly indicates a collection. Naming does not replace API documentation, but helps callers read the intended semantics.

### 1.1. Why Is Optional<List<T>> Usually Inappropriate?

List already expresses "no elements" via an empty list. Returning Optional<List<User>> forces callers to guess:

- Does Optional.empty() mean not queried, empty database, or unauthorized?
- Does Optional.of(List.of()) mean anything different from Optional.empty()?
- When should these two empty states be used?

For normal collection queries, simply use **List<User>** and return **List.of()** or the empty list produced by JdbcTemplate. Only use a richer model when business rules genuinely distinguish "not executed" from "executed with no results"; even then, an explicitly named result state type is clearer than Optional<List<T>>.

## 2. Four Distinct Scenarios: 0 Rows, 1 Row, Multiple Rows, SQL NULL

To keep examples consistent, create a practice table:

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    nickname VARCHAR(120),
    status VARCHAR(20) NOT NULL
);

INSERT INTO app_users (id, email, display_name, nickname, status)
VALUES
    (1, 'lan@example.test', 'Lan', NULL, 'ACTIVE'),
    (2, 'minh@example.test', 'Lan', 'M', 'ACTIVE'),
    (3, 'an@example.test', 'An', NULL, 'INACTIVE');
~~~

The table has primary key id, unique key email, while display_name is **not unique** and nickname **allows NULL**. Compare:

~~~sql
-- No rows:
SELECT nickname FROM app_users WHERE id = 999;

-- 1 row, nickname column is SQL NULL:
SELECT nickname FROM app_users WHERE id = 1;

-- 1 row with nickname = 'M':
SELECT nickname FROM app_users WHERE id = 2;

-- 2 ACTIVE rows:
SELECT id, email FROM app_users WHERE status = 'ACTIVE';
~~~

| SQL | Row count | Value | Meaning |
| --- | ---: | --- | --- |
| id = 999 | 0 | No record | User does not exist |
| id = 1 | 1 | nickname = NULL | User exists, but nickname is not set |
| id = 2 | 1 | nickname = M | User exists and nickname has a value |
| status = ACTIVE | 2 | Two different users | Valid collection query |

**Zero rows does not mean one row with SQL NULL.** If a repository returns Optional<User>, user id=1 must be **Optional present** where RowMapper creates a User object with a null nickname field. If a repository queries only nickname and wraps it in Optional.ofNullable, both situations above become empty; that is acceptable only if the contract asks "does nickname have a value?" rather than "does the user exist?".

**Database errors** are also a separate state: invalid SQL, connection loss, timeouts, permission errors, or mapping failures must never be interpreted as "not found".

## 3. JdbcTemplate.query(...) for 0..n: An Empty List Is Valid

In Spring JDBC, query(String, RowMapper, Object...) maps each row of the ResultSet and returns a **List<T>**. When SQL returns 0 rows, the returned list is **empty**, not null.

~~~java
List<UserRow> users = jdbcTemplate.query(
    """
    SELECT id, email, display_name, nickname
    FROM app_users
    WHERE status = ?
    ORDER BY id
    """,
    (rs, rowNum) -> new UserRow(
        rs.getLong("id"),
        rs.getString("email"),
        rs.getString("display_name"),
        rs.getString("nickname")
    ),
    "ACTIVE"
);
~~~

The snippet above is part of an application that has declared jdbcTemplate and record UserRow; it is not a standalone program. With the sample data, users.size() equals **2**; for a non-existent status, users.isEmpty() is true.

Repository example:

~~~java
public List<UserRow> findByStatus(String status) {
    return jdbc.query(
        """
        SELECT id, email, display_name, nickname
        FROM app_users
        WHERE status = ?
        ORDER BY id
        """,
        USER_ROW_MAPPER,
        status
    );
}
~~~

Callers use **isEmpty()**, **size()**, and **forEach(...)** normally. Never write repository code that converts an empty list into null, forcing every caller into pointless null checks.

### 3.1. NamedParameterJdbcTemplate Follows the Same Rule

~~~java
List<UserRow> found = namedJdbc.query(
    """
    SELECT id, email, display_name, nickname
    FROM app_users
    WHERE status = :status
    ORDER BY id
    """,
    java.util.Map.of("status", "ACTIVE"),
    USER_ROW_MAPPER
);
~~~

The difference is that **:status** is bound by name. Cardinality behavior matches JdbcTemplate: query returns 0..n, queryForObject requires exactly one. Do not mistakenly assume named parameters automatically turn results into Optional.

## 4. JdbcTemplate.queryForObject(...) for Exactly One Row

queryForObject is strict about **row count**. With the RowMapper overload:

~~~java
UserRow user = jdbc.queryForObject(
    """
    SELECT id, email, display_name, nickname
    FROM app_users
    WHERE id = ?
    """,
    USER_ROW_MAPPER,
    1L
);
~~~

Behavior per Javadoc:

| ResultSet | queryForObject Behavior |
| --- | --- |
| 0 rows | **EmptyResultDataAccessException** |
| Exactly 1 row | Returns object mapped by RowMapper; may be null if RowMapper explicitly returns null |
| 2+ rows | **IncorrectResultSizeDataAccessException** |
| SQL/driver/DB error | An appropriate **DataAccessException** after Spring's error translation |

EmptyResultDataAccessException is a subclass of IncorrectResultSizeDataAccessException, because "0 rows" is also an invalid size when expecting exactly one. If code catches IncorrectResultSizeDataAccessException and returns Optional.empty(), it will **swallow the 2+ rows case**, which is dangerous when a query or data is broken.

### 4.1. Scalar Queries and SQL NULL

The queryForObject(sql, Integer.class, args...) overload expects **exactly one row, one column**. If the row exists and the column is SQL NULL, the result can be Java null:

~~~java
Integer result = jdbc.queryForObject(
    "SELECT CAST(NULL AS INTEGER)",
    Integer.class
);
// result == null: one row exists, but column value is SQL NULL.
~~~

Compare with:

~~~java
Integer result = jdbc.queryForObject(
    "SELECT id FROM app_users WHERE id = ?",
    Integer.class,
    999L
);
// 0 rows -> EmptyResultDataAccessException, NOT null.
~~~

Keep this in mind when reading API docs: returning null **can represent SQL NULL** in scalar queries, whereas zero rows normally raises an exception.

### 4.2. Mistake: Optional.ofNullable(queryForObject(...))

~~~java
// This does NOT turn 0 rows into Optional.empty().
Optional<UserRow> user = Optional.ofNullable(
    jdbc.queryForObject(
        "SELECT id, email, display_name, nickname " +
        "FROM app_users WHERE id = ?",
        USER_ROW_MAPPER,
        id
    )
);
~~~

The queryForObject call is evaluated first; on 0 rows it throws EmptyResultDataAccessException, so Optional.ofNullable is **never invoked**. Change the API choice or handle the exception properly.

## 5. Designing findById with Optional<T>

### 5.1. Clean Approach with query and DataAccessUtils.optionalResult

Since **Spring Framework 6.1**, DataAccessUtils provides optionalResult(Collection), converting a 0..1 cardinality collection into Optional.

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.dao.support.DataAccessUtils;

public Optional<UserRow> findById(long id) {
    List<UserRow> rows = jdbc.query(
        """
        SELECT id, email, display_name, nickname
        FROM app_users
        WHERE id = ?
        """,
        USER_ROW_MAPPER,
        id
    );
    return DataAccessUtils.optionalResult(rows);
}
~~~

Specific cases:

- 0 elements: **Optional.empty()**.
- 1 non-null element: **Optional containing UserRow**.
- More than 1 element: **IncorrectResultSizeDataAccessException**.
- 1 null element: Optional cannot hold null, so **Optional.empty()**.

That last point matters: a domain RowMapper should always build **a non-null object** for a valid row. If a mapper returns null due to bad field data, optionalResult can hide the difference between "invalid existing row" and "no row". Enforce constraints in the DB, map nullable fields properly, and throw an error when a row cannot be mapped.

DataAccessUtils also has **singleResult(Collection)** returning null on 0 rows and throwing on >1; and **requiredSingleResult(Collection)** requiring one non-null object; do not confuse them with optionalResult. Check your Spring version before calling optionalResult, as Spring 6.0 does not have it.

### 5.2. Using queryForObject and Catching EmptyResultDataAccessException Specifically

If a project uses an older Spring version or a repository prefers keeping queryForObject:

~~~java
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;

public Optional<UserRow> findById(long id) {
    try {
        UserRow value = jdbc.queryForObject(
            """
            SELECT id, email, display_name, nickname
            FROM app_users
            WHERE id = ?
            """,
            USER_ROW_MAPPER,
            id
        );
        return Optional.ofNullable(value);
    } catch (EmptyResultDataAccessException missing) {
        return Optional.empty();
    }
}
~~~

**Catch only EmptyResultDataAccessException** to turn "0 rows" into an allowed absence. Never catch all DataAccessException; lost connections, permission errors, SQL bugs, or duplicate data are real failures that must be handled and monitored.

Likewise, never write **catch (Exception e) { return Optional.empty(); }**. That masks both programming bugs and database outages, making the system report "user does not exist" while the database is down.

## 6. Spring JdbcClient: optional() and single() (Spring 6.1+)

**JdbcClient** is the fluent API introduced in Spring 6.1, layered over JdbcTemplate/NamedParameterJdbcTemplate and supporting positional or named parameters. With a RowMapper:

~~~java
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;

public Optional<UserRow> findById(long id) {
    return jdbcClient
        .sql("""
             SELECT id, email, display_name, nickname
             FROM app_users
             WHERE id = :id
             """)
        .param("id", id)
        .query(USER_ROW_MAPPER)
        .optional();
}
~~~

The snippet belongs to a repository with fields jdbcClient and USER_ROW_MAPPER. optional() on **JdbcClient.MappedQuerySpec** enforces 0..1 cardinality: 0 rows -> Optional.empty(), 1 row -> Optional present, >1 row -> error.

Other options:

~~~java
// Collection query, 0..n.
List<UserRow> users = jdbcClient
    .sql("SELECT id, email, display_name, nickname " +
         "FROM app_users WHERE status = :status ORDER BY id")
    .param("status", "ACTIVE")
    .query(USER_ROW_MAPPER)
    .list();

// Query requiring exactly one UserRow.
UserRow required = jdbcClient
    .sql("SELECT id, email, display_name, nickname " +
         "FROM app_users WHERE id = :id")
    .param("id", 1L)
    .query(USER_ROW_MAPPER)
    .single();
~~~

**Versions:** MappedQuerySpec.optional() and JdbcClient were introduced in Spring **6.1**. The **ResultQuerySpec.optionalValue()** API for single-column value queries was added in Spring **6.2**; do not assume every newer convenience method exists in 6.1. Check Javadoc for your exact version, especially when Spring Boot manages Spring Framework versions.

## 7. Mandatory Records: Should Repository or Service Throw?

Some queries allow "does not exist", while certain business operations require the record to exist. Separating the contract:

~~~java
public interface AccountRepository {
    Optional<Account> findById(long id);
    Account getRequiredById(long id);
}
~~~

**Account** is a domain class defined in the application. A common pattern is having the repository return Optional while the service decides the business error:

~~~java
public Account requireAccount(long accountId) {
    return accountRepository.findById(accountId)
        .orElseThrow(() -> new AccountNotFoundException(accountId));
}
~~~

**AccountNotFoundException** is an application-defined exception. Alternatively, getRequiredById can throw a specific business exception on absence, provided it is consistent and well documented.

**Keep HTTP out of JDBC repositories:** a repository should not throw HTTP 404/ResponseStatusException directly. The service handles "business not found", and a REST controller or @ControllerAdvice maps it to 404 if appropriate. A scheduled job or message consumer may handle the exact same absence differently.

Also distinguish **does not exist** from **not authorized to view**. A query filtered by tenant/authorization may omit records the user is not allowed to see; whether to expose 403 or 404 is an upper-layer security policy. Avoid accidentally leaking resource existence through errors, logs, or response timing.

## 8. Querying by Unique Key and Protecting Cardinality via Schema

The Optional<User> contract for ID/email rests on the assumption that SQL matches at most one row. **PRIMARY KEY** and **UNIQUE constraints** are how the database enforces that assumption.

If display names are not unique:

~~~sql
SELECT id, email, display_name, nickname
FROM app_users
WHERE display_name = 'Lan';
~~~

The sample result has **2 rows**. Never implement findByDisplayName returning Optional<User> by "taking the first element" unless business rules explicitly define which one to pick. The right contract is usually List<User> findByDisplayName(...).

### 8.1. LIMIT 1 Can Mask Bad Data

~~~sql
SELECT id, email, display_name, nickname
FROM app_users
WHERE display_name = 'Lan'
LIMIT 1;
~~~

This returns one row without guaranteeing which row if ORDER BY is missing. Adding LIMIT 1 **does not fix** a "must be unique" contract; it can mask duplicates caused by bad data or broken JOINs.

If the real requirement is "most recently updated record", name the method accordingly, use ORDER BY updated_at DESC, id DESC and LIMIT 1. Then picking one among many **is the stated business rule**, and returning Optional when none exists is appropriate.

### 8.2. LIMIT 2 to Detect Multiple Rows

If a query expects 0..1 without a strong enough DB constraint yet and you want efficient checking:

~~~sql
SELECT id, email, display_name, nickname
FROM app_users
WHERE email = ?
LIMIT 2;
~~~

Combine query(...) returning List with optionalResult(List): 2 rows -> cardinality error; 0 or 1 handled normally. This only reduces data transferred to Java when detecting duplicates; it does not replace a UNIQUE constraint. LIMIT syntax also depends on the DBMS.

## 9. COUNT, EXISTS, and Cases Where Optional Should Not Be Used

The question "does a user exist?" usually needs a boolean, not Optional<User>, if the caller does not need user data:

~~~java
public boolean existsById(long id) {
    Integer count = jdbc.queryForObject(
        "SELECT COUNT(*) FROM app_users WHERE id = ?",
        Integer.class,
        id
    );
    if (count == null) {
        throw new IllegalStateException("COUNT(*) returned NULL");
    }
    return count > 0;
}
~~~

**SELECT COUNT(*) without GROUP BY** returns one row with the count; when no rows match, the value is **0**, not 0 rows. Hence long/int is a better contract than Optional<Long>. Depending on DBMS and workload, EXISTS can be more optimal than COUNT(*) for existence checks.

Similarly:

~~~sql
SELECT MAX(id) FROM app_users WHERE status = 'UNKNOWN';
~~~

An aggregate query without GROUP BY normally **returns one row**, though MAX can be **SQL NULL** when there are no values to aggregate. With queryForObject(..., Long.class), Java can receive null. If the business rule wants "max value may be undefined", Optional<Long> can fit, provided you understand it denotes the absence of an **aggregate value**, not JDBC returning zero rows.

## 10. Using Optional in Services: map, orElseGet, and orElseThrow

~~~java
Optional<UserRow> found = repository.findById(userId);

// Transform only when the object exists.
Optional<String> email = found.map(UserRow::email);

// Explicit business error when existence is mandatory.
UserRow required = found.orElseThrow(
    () -> new UserNotFoundException(userId)
);

// Perform a side effect when present.
found.ifPresent(user -> audit.recordFound(user.id()));
~~~

This is an illustrative snippet; variables repository, userId, audit, and UserNotFoundException must be declared in the application.

Points to remember:

- **Optional.get()** throws a generic NoSuchElementException when empty; prefer orElseThrow with business context.
- **orElse(expensiveDefault())** evaluates expensiveDefault even when Optional is present, because Java evaluates method arguments eagerly. When you want to compute a fallback only if empty, use **orElseGet(() -> expensiveDefault())**.
- **Optional.orElse(null)** may be needed for legacy integration code, though passing null across layers undermines the Optional contract.
- A method returning Optional<T> **must never return null instead of Optional.empty()**.
- Optional fits primarily as the **return type** of 0..1 queries; avoid using Optional by default as entity fields, repository parameters, or serialized DTO fields.

**Optional does not make SQL run faster.** It simply communicates data state to callers more clearly.

## 11. When Business Logic Has More Than Two States

Optional represents only **present/absent**. By itself it cannot express:

- Not found.
- Record exists, but caller is denied permission.
- Record is disabled.
- Query failed due to database, network, or timeout.

If all of these are normal business states requiring different caller reactions, design a **dedicated result type** instead of collapsing everything into Optional.empty():

~~~java
public sealed interface AccountLookup
        permits AccountLookup.Found,
                AccountLookup.Missing,
                AccountLookup.Disabled {

    record Found(Account account) implements AccountLookup {}
    record Missing(long accountId) implements AccountLookup {}
    record Disabled(long accountId) implements AccountLookup {}
}
~~~

This is a Java 17 example with an application-defined Account type. Never turn a database error into a Missing state to make a failed query look successful. Introduce this pattern only when genuinely needed; for standard ID lookups, Optional<User> suffices.

## 12. Runnable Example: Demonstrating 0 Rows, 1 Row, 2 Rows, and SQL NULL

This example uses **Java 17+**, **Spring JDBC 6.2.7**, and **H2 2.3.232**, creating data in memory. Gradle manages the Spring JDBC/H2 jars. The goal is to clarify contract outputs without depending on a Spring Boot web server.

Structure:

~~~text
jdbc-contract-demo/
  build.gradle
  src/main/java/demo/RepositoryContractDemo.java
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.7'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.RepositoryContractDemo'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

File **src/main/java/demo/RepositoryContractDemo.java**:

~~~java
package demo;

import java.util.List;
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class RepositoryContractDemo {

    record UserRow(long id, String email, String displayName) {}

    interface UserRepository {
        Optional<UserRow> findById(long id);
        List<UserRow> findByDisplayName(String displayName);
        UserRow requireById(long id);
    }

    static final class JdbcUserRepository implements UserRepository {
        private static final RowMapper<UserRow> MAPPER =
                (rs, rowNum) -> new UserRow(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("display_name")
                );

        private final JdbcTemplate jdbc;

        JdbcUserRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        public Optional<UserRow> findById(long id) {
            List<UserRow> rows = jdbc.query(
                """
                SELECT id, email, display_name
                FROM app_users
                WHERE id = ?
                """,
                MAPPER,
                id
            );
            return DataAccessUtils.optionalResult(rows);
        }

        @Override
        public List<UserRow> findByDisplayName(String displayName) {
            return jdbc.query(
                """
                SELECT id, email, display_name
                FROM app_users
                WHERE display_name = ?
                ORDER BY id
                """,
                MAPPER,
                displayName
            );
        }

        @Override
        public UserRow requireById(long id) {
            return jdbc.queryForObject(
                """
                SELECT id, email, display_name
                FROM app_users
                WHERE id = ?
                """,
                MAPPER,
                id
            );
        }
    }

    public static void main(String[] args) {
        DriverManagerDataSource source = new DriverManagerDataSource(
            "jdbc:h2:mem:contract_demo;DB_CLOSE_DELAY=-1",
            "sa",
            ""
        );
        JdbcTemplate jdbc = new JdbcTemplate(source);

        jdbc.execute(
            """
            CREATE TABLE app_users (
                id BIGINT PRIMARY KEY,
                email VARCHAR(120) NOT NULL UNIQUE,
                display_name VARCHAR(120) NOT NULL
            )
            """
        );
        jdbc.update(
            "INSERT INTO app_users (id, email, display_name) " +
            "VALUES (?, ?, ?)",
            1L, "lan@example.test", "Lan"
        );
        jdbc.update(
            "INSERT INTO app_users (id, email, display_name) " +
            "VALUES (?, ?, ?)",
            2L, "minh@example.test", "Lan"
        );

        UserRepository repo = new JdbcUserRepository(jdbc);
        System.out.println("findById(99): " + repo.findById(99L));
        System.out.println(
            "findById(1).email: " +
            repo.findById(1L).map(UserRow::email).orElse("none")
        );
        System.out.println(
            "findByDisplayName(Nobody).size: " +
            repo.findByDisplayName("Nobody").size()
        );
        System.out.println(
            "findByDisplayName(Lan).size: " +
            repo.findByDisplayName("Lan").size()
        );

        try {
            repo.requireById(99L);
        } catch (EmptyResultDataAccessException ex) {
            System.out.println(
                "requireById(99): " + ex.getClass().getSimpleName()
            );
        }

        try {
            jdbc.queryForObject(
                """
                SELECT id, email, display_name
                FROM app_users WHERE display_name = ?
                """,
                (rs, rowNum) -> new UserRow(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("display_name")
                ),
                "Lan"
            );
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println(
                "multiple rows: " + ex.getClass().getSimpleName()
            );
        }

        Integer nullableValue = jdbc.queryForObject(
            "SELECT CAST(NULL AS INTEGER)",
            Integer.class
        );
        System.out.println("one SQL NULL: " + nullableValue);
    }
}
~~~

Run in the directory containing build.gradle with Gradle installed:

~~~bash
gradle run
~~~

If the project has a Gradle Wrapper, use:

~~~bash
./gradlew run
~~~

On Windows PowerShell, if the Wrapper is present:

~~~powershell
.\gradlew.bat run
~~~

Do not run `javac RepositoryContractDemo.java` standalone without supplying the Spring JDBC/H2 classpath, as the Java compiler will lack the packages. Gradle resolves dependencies; the classes use Java 17 records and text blocks.

**Program stdout** (excluding Gradle build/log lines):

~~~text
findById(99): Optional.empty
findById(1).email: lan@example.test
findByDisplayName(Nobody).size: 0
findByDisplayName(Lan).size: 2
requireById(99): EmptyResultDataAccessException
multiple rows: IncorrectResultSizeDataAccessException
one SQL NULL: null
~~~

Explanation:

1. ID 99 does not exist -> findById returns Optional.empty().
2. ID 1 has a user -> Optional holds UserRow; map extracts email.
3. No displayName Nobody -> empty List.
4. Two users named Lan -> List contains two records, which is valid for findByDisplayName.
5. requireById requires exactly one record -> queryForObject throws EmptyResultDataAccessException on 0 rows.
6. queryForObject by non-UNIQUE displayName receives 2 rows -> IncorrectResultSizeDataAccessException.
7. SELECT CAST(NULL AS INTEGER) returns one row with SQL NULL -> Java null value.

The demo uses **DriverManagerDataSource** to minimize setup, not as a connection pool. Production systems typically use HikariCP/DataSource managed by Spring Boot, schema migrations, and transaction boundaries at the service layer.

## 13. Tests That Truly Add Value

Repository tests must verify **SQL semantics and cardinality**, not merely whether a method was called.

| Test case | Setup | Expected |
| --- | --- | --- |
| Find by missing ID | Non-existent ID | Optional.empty() |
| Find by existing ID | One valid record | Optional present with right ID/email |
| 0..1 query unexpectedly has multiple rows | Query/JOIN returns 2+ rows | IncorrectResultSizeDataAccessException |
| Search empty set | No record matches status | Empty list, non-null |
| Search multi-item set | Two records | List has both in proper ORDER BY order |
| Nullable field | User has SQL NULL nickname | Optional<User> present, nickname null |
| Invalid SQL/schema | Wrong table/column name | DataAccessException, not empty |
| DB timeout/disconnect | DB infrastructure unresponsive | Data/connection error, not empty |
| Service requires mandatory ID | Repo returns Optional.empty() | Appropriate business exception |
| Tenant/permission | ID outside query scope | No data leaked via API |

Mock-based unit tests must never assume **JdbcTemplate.query(...) returns null on 0 rows**; the standard behavior is an empty List. For SQL using PostgreSQL/MySQL-specific features, test against the real DBMS or an appropriate integration test (such as Testcontainers); H2 does not completely emulate every DBMS's semantics.

### 13.1. Service Tests Differ from Repository Tests

Repository tests verify converting JDBC rows into Optional/List and preserving technical errors. Service tests verify turning Optional.empty() into business exceptions when existence is mandatory, or returning proper outcomes when absence is permitted. REST controller tests map business exceptions to HTTP responses if needed. Do not repeat the exact same assertions across all three layers.

## 14. Performance, Streams, and Concurrency

**Optional is only a Java type**; it does not reduce query latency. Real optimization lies in SQL, indexes, cardinality, connections, and transactions.

If a query can return a large set, JdbcClient/JdbcTemplate also supports stream/RowCallbackHandler processing. Streams tied to JDBC resources must be closed per API rules (usually try-with-resources); never return a Stream holding an open ResultSet from a repository to a caller without a clear lifecycle contract.

Beware of **check-then-act race conditions**: an Optional<User> populated at lookup time does not guarantee the record still exists right before a subsequent UPDATE. If business logic must modify data atomically, consider UPDATE ... WHERE ... and check affected row counts, or design appropriate transactions/locking. Optional does not provide isolation.

When detecting duplicate data without loading an entire dataset, `LIMIT 2` with `optionalResult` can be more efficient, though a unique constraint in the schema is still required for correctness.

## 15. Common Mistakes

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| Optional.ofNullable(queryForObject(...)) to catch 0 rows | queryForObject throws before Optional is called | query + optionalResult; JdbcClient.optional; or catch EmptyResultDataAccessException specifically |
| catch (DataAccessException) then return Optional.empty() | Hides SQL, DB, timeout, and duplicate errors | Convert only 0 rows to empty |
| Catching IncorrectResultSizeDataAccessException for every absence | Swallows >1 row errors too | Catch the specific EmptyResultDataAccessException subclass |
| Returning null for an empty List | Callers must check for null | Return an empty List |
| Returning null instead of Optional.empty() | Breaks the Optional contract | Always return a valid Optional |
| Optional<List<User>> for 0..n results | Two ambiguous ways to be empty | Use List<User> |
| findByDisplayName using queryForObject when name is not UNIQUE | Cardinality error when two people share a name | Use List or change the condition |
| Adding LIMIT 1 to mask duplicates | Drops records or picks arbitrarily | Unique constraint or explicit ORDER BY rule |
| Treating one row with a NULL column as 0 rows | Loses existence information | Map the full entity with nullable fields |
| Calling Optional.get() blindly when empty | NoSuchElementException without context | map, orElseGet, orElseThrow |
| Having repository throw HTTP 404 | Couples JDBC to REST transport | Let service/controller handle transport |
| Thinking COUNT(*) == 0 means an empty ResultSet | Wrong cardinality for aggregates | Handle the 0 count value |
| Using Optional for every method | Pointlessly complicates the API | Choose return type by cardinality |

## 16. Self-Check Exercises

**Exercise 1.** findById(999) is declared Optional<User> and SQL returns 0 rows. What is the right outcome?

**Answer:** Optional.empty(), because a missing record is a valid outcome of a 0..1 query.

**Exercise 2.** findByStatus("ARCHIVED") is declared List<User> and finds no rows. Should it return Optional.empty(), null, or an empty List?

**Answer:** An empty List; having zero items is not an error in a collection query.

**Exercise 3.** Does queryForObject with a non-existent ID return null?

**Answer:** No, it normally throws EmptyResultDataAccessException because the query did not return exactly one row.

**Exercise 4.** A user row exists, yet nickname is SQL NULL. Can Optional<UserRow> be present?

**Answer:** Yes. RowMapper constructs a non-null UserRow with a null nickname. Optional represents **record** existence, not that every field is populated.

**Exercise 5.** Does Optional.ofNullable(jdbc.queryForObject(...)) turn 0 rows into Optional.empty()?

**Answer:** No. The exception is thrown before ofNullable executes.

**Exercise 6.** DataAccessUtils.optionalResult receives a List containing 2 Users. Does it pick the first and ignore the rest?

**Answer:** No. It throws IncorrectResultSizeDataAccessException to report the 0..1 contract violation.

**Exercise 7.** Does using LIMIT 1 on a non-unique name query make name a unique key?

**Answer:** No. You need a UNIQUE constraint or a clearly defined ordered selection rule.

**Exercise 8.** Does COUNT(*) on an empty set normally return 0 rows or one row with value 0?

**Answer:** One row with value 0 when there is no GROUP BY. Thus repositories normally return a count, not Optional.

**Exercise 9.** JDBC loses connection during findById. Should it return Optional.empty() so callers don't fail?

**Answer:** No. "Unable to query" cannot prove "does not exist"; technical errors must be handled and observed.

**Exercise 10.** A service gets Optional<User> from a repo. What is a clearer way than get() to express "user must exist"?

**Answer:** orElseThrow(() -> new UserNotFoundException(id)) with an application-defined business exception.

## 17. JDBC Repository Design Checklist

1. **Determine cardinality** of the query before coding: 0..1, exactly 1, 0..n, or scalar count.
2. **Write meaningful signatures:** Optional<T> for 0..1; List<T> for 0..n; required value for exactly 1.
3. **Distinguish clearly:** 0 rows, one row with SQL NULL, >1 row, database errors, and unauthorized access.
4. **Pick the right Spring API:** query(...) for List, queryForObject(...) for exactly one, optionalResult/JdbcClient.optional() for 0..1.
5. **Translate only the absence error** into Optional.empty; never swallow general DataAccessException.
6. **Protect via schema:** PRIMARY KEY, UNIQUE, and proper JOIN/WHERE. Never use LIMIT 1 to mask duplicates.
7. **Keep RowMapper clear:** each valid row builds one object, mapping nullable fields intentionally.
8. **Separate decisions by layer:** repository manages data, service sets business rules, controller sets HTTP status.
9. **Test 0/1/n**, SQL NULL, duplicates, data access errors, access control, and transactions.
10. **Check versions:** DataAccessUtils.optionalResult and JdbcClient are in Spring 6.1+; single-value optionalValue helper is in 6.2+.

### Official References

- Spring Framework JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- JdbcOperations Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
- DataAccessUtils Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/support/DataAccessUtils.html
- JdbcClient Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- JdbcClient.MappedQuerySpec Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
