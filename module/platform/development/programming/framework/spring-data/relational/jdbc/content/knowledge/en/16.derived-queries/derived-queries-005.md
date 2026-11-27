# IsNull, IsNotNull, True, and False Conditions

In **Spring Data Relational JDBC**, derived queries let you express query conditions directly in repository method names. Four commonly used conditions are:

- **IsNull:** finds rows where the property has the SQL value `NULL`.
- **IsNotNull:** finds rows where the property has a non-`NULL` value.
- **True:** finds rows where the boolean property is `TRUE`.
- **False:** finds rows where the boolean property is `FALSE`.

These keywords are useful when querying unfilled data, soft-deleted records, enabled/disabled statuses, and business flags. However, you must understand SQL `NULL` semantics properly: `NULL` is not `FALSE`, and comparisons against `NULL` do not behave like comparisons between ordinary values.

This lesson explains method name syntax, how Spring Data JDBC translates conditions into SQL queries, how to combine multiple predicates, and common pitfalls when using nullable `Boolean` types.

## 1. Derived Queries in Spring Data JDBC

Spring Data JDBC can generate queries from repository method names. Instead of writing SQL manually for simple conditions, you declare method names following query derivation rules.

Example:

```java
public interface UserAccountRepository
        extends CrudRepository<UserAccount, Long> {

    List<UserAccount> findByDeletedAtIsNull();

    List<UserAccount> findByDeletedAtIsNotNull();

    List<UserAccount> findByEnabledTrue();

    List<UserAccount> findByEnabledFalse();
}
```

Spring Data parses the method name to identify:

- **Subject:** describes the result/operation type, such as `find`, `count`, `exists`.
- **Predicate:** the part after `By`, describing properties and conditions.
- **Property path:** the Java property name to query.
- **Operator/keyword:** conditions like `IsNull`, `IsNotNull`, `True`, `False`, `And`, `Or`.

For example, `findByDeletedAtIsNull()` means: find `UserAccount` records whose `deletedAt` property is currently null. `findByEnabledTrue()` means: find accounts where `enabled` equals true.

**The property name in the method is the Java property name**, not the SQL column name. If `deletedAt` maps to the `deleted_at` column, the method still uses `DeletedAt`.

## 2. IsNull: Finding Properties with NULL Values

`IsNull` represents the SQL `IS NULL` condition.

For example, an account that has not been soft-deleted has `deletedAt = null`:

```java
List<UserAccount> findByDeletedAtIsNull();
```

Another method:

```java
List<UserAccount> findByEmailIsNull();
```

Corresponding SQL semantics:

```sql
SELECT *
FROM user_accounts
WHERE deleted_at IS NULL;
```

Or:

```sql
SELECT *
FROM user_accounts
WHERE email IS NULL;
```

No parameter is passed to `IsNull`, because the condition does not compare the property with a caller-supplied value. It checks the column's null state directly.

### 2.1. The Null alias

Spring Data query derivation supports both `IsNull` and `Null` for null checks. For example:

```java
List<UserAccount> findByDeletedAtNull();
```

However, `IsNull` is usually easier to read because it clearly reads as a null-check predicate.

### 2.2. When to use IsNull?

Common scenarios:

| Property | Meaning of NULL | Example method |
|---|---|---|
| `deletedAt` | Record has not been soft-deleted | `findByDeletedAtIsNull()` |
| `verifiedAt` | Not yet verified | `findByVerifiedAtIsNull()` |
| `publishedAt` | Not yet published | `findByPublishedAtIsNull()` |
| `assignedTo` | Not yet assigned to a handler | `findByAssignedToIsNull()` |
| `closedAt` | Ticket not yet closed | `findByClosedAtIsNull()` |

Only use `IsNull` when null has a clear domain meaning. Do not use null as an arbitrary stand-in for multiple distinct states.

## 3. IsNotNull: Finding Properties with Non-Null Values

`IsNotNull` represents SQL `IS NOT NULL`.

Example:

```java
List<UserAccount> findByDeletedAtIsNotNull();

List<UserAccount> findByEmailIsNotNull();
```

Semantically equivalent SQL:

```sql
SELECT *
FROM user_accounts
WHERE deleted_at IS NOT NULL;
```

```sql
SELECT *
FROM user_accounts
WHERE email IS NOT NULL;
```

This method returns rows where the column holds a value, even if that value is an empty string or zero. `IS NOT NULL` does not check whether the content is valid; it only checks whether the column is SQL NULL.

### 3.1. The NotNull alias

You can write `NotNull` instead of `IsNotNull`:

```java
List<UserAccount> findByEmailNotNull();
```

Both express the same condition. Keep a consistent naming convention across the codebase so repositories remain easy to read.

### 3.2. IsNotNull does not mean non-empty string

For example:

| `email` in database | `email IS NOT NULL` |
|---|---|
| `NULL` | Does not match |
| Empty string (`''`) | Matches |
| Whitespace only (`'   '`) | Matches |
| `linh@example.com` | Matches |

If business logic requires a non-empty string, you need another condition such as `Not` against an empty string, validation, or an explicit query. `IsNotNull` does not trim or check string length.

## 4. True and False: Boolean Conditions

For boolean properties, Spring Data supports the `True` and `False` keywords.

Example:

```java
List<UserAccount> findByEnabledTrue();

List<UserAccount> findByEnabledFalse();
```

The two methods mean:

- `findByEnabledTrue()`: selects only rows where `enabled = TRUE`.
- `findByEnabledFalse()`: selects only rows where `enabled = FALSE`.

You can also use the `IsTrue` and `IsFalse` aliases:

```java
List<UserAccount> findByEnabledIsTrue();

List<UserAccount> findByEnabledIsFalse();
```

Both naming styles express the same predicate. `True`/`False` are usually shorter and easier to read.

### 4.1. Corresponding SQL

On a database with a `BOOLEAN` type, the query semantics resemble:

```sql
SELECT *
FROM user_accounts
WHERE enabled = TRUE;
```

and:

```sql
SELECT *
FROM user_accounts
WHERE enabled = FALSE;
```

Specific boolean literal syntax can vary across database engines. Spring Data JDBC uses the database dialect and mapping to construct the query; do not substitute `= 1` or `= 'Y'` without considering the database and column type.

### 4.2. True/False are not IsNull/IsNotNull

If a property is a `Boolean` (wrapper) and the column allows NULL, there are three data states:

1. `TRUE`
2. `FALSE`
3. `NULL`

`findByEnabledTrue()` finds only the first state. `findByEnabledFalse()` finds only the second state. Neither returns rows where `enabled = NULL`.

If you need to query the third state, use `findByEnabledIsNull()`.

## 5. SQL NULL and Three-Valued Logic

This is the most important concept when combining null and boolean conditions.

In SQL, a conditional expression can evaluate to:

- `TRUE`
- `FALSE`
- `UNKNOWN`

When a comparison involves `NULL`, the result is usually `UNKNOWN`, not `TRUE` or `FALSE`.

For example:

```sql
enabled = TRUE
enabled = FALSE
enabled <> TRUE
enabled = NULL
```

If `enabled` is NULL, none of these comparisons evaluate to TRUE. Because `WHERE` only keeps rows for which the predicate evaluates to TRUE, rows with NULL will not appear in the results.

To test for null, SQL requires the syntax:

```sql
enabled IS NULL
enabled IS NOT NULL
```

Summary truth table:

| `enabled` value | `enabled = TRUE` | `enabled = FALSE` | `enabled IS NULL` | `enabled IS NOT NULL` |
|---|---|---|---|---|
| TRUE | TRUE | FALSE | FALSE | TRUE |
| FALSE | FALSE | TRUE | FALSE | TRUE |
| NULL | UNKNOWN | UNKNOWN | TRUE | FALSE |

This is why `findByEnabledFalse()` does not mean "not true, including null." It strictly means "equal to false."

### 5.1. Finding false or unset values

If business logic treats both `FALSE` and `NULL` as not enabled, express both conditions:

```java
List<UserAccount> findByEnabledFalseOrEnabledIsNull();
```

SQL semantics:

```sql
SELECT *
FROM user_accounts
WHERE enabled = FALSE
   OR enabled IS NULL;
```

Similarly, if you need accounts that are enabled or do not yet have a status set:

```java
List<UserAccount> findByEnabledTrueOrEnabledIsNull();
```

Determine the business meaning of null before combining conditions. Null might mean "not yet configured," "unknown," "not applicable," or "legacy unmigrated data." Do not automatically fold null into false if the domain needs to distinguish them.

## 6. Complete Domain and Repository Example

Suppose the `user_accounts` table stores user accounts, including email, activation status, verification status, and soft-delete timestamp.

### 6.1. Schema

Example DDL for PostgreSQL:

```sql
CREATE TABLE user_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255),
    enabled BOOLEAN,
    verified BOOLEAN,
    deleted_at TIMESTAMP
);
```

In this example:

- `email` allows NULL to illustrate `IsNull`.
- `enabled` and `verified` are nullable `BOOLEAN` columns.
- `deleted_at` allows NULL; NULL means the account has not been soft-deleted.

A production schema might also add `NOT NULL`, unique constraints, indexes, and other business constraints. If `enabled` must always have a value, declare it `NOT NULL` and consider backfilling existing data before applying the constraint.

### 6.2. Domain class

```java
import java.time.LocalDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("user_accounts")
public class UserAccount {

    @Id
    private Long id;

    private String email;

    private Boolean enabled;

    private Boolean verified;

    @Column("deleted_at")
    private LocalDateTime deletedAt;

    protected UserAccount() {
    }

    public UserAccount(
            String email,
            Boolean enabled,
            Boolean verified
    ) {
        this.email = email;
        this.enabled = enabled;
        this.verified = verified;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public Boolean getVerified() {
        return verified;
    }

    public LocalDateTime getDeletedAt() {
        return deletedAt;
    }
}
```

Annotations and data types:

- `@Table` is the Spring Data Relational annotation for mapping the table.
- `@Id` is the Spring Data annotation indicating the identifier.
- `@Column("deleted_at")` maps the `deletedAt` property to the `deleted_at` column.
- `Boolean` can represent true, false, and null.

### 6.3. Repository

```java
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface UserAccountRepository
        extends CrudRepository<UserAccount, Long> {

    // Null predicates
    List<UserAccount> findByEmailIsNull();

    List<UserAccount> findByEmailIsNotNull();

    List<UserAccount> findByDeletedAtIsNull();

    List<UserAccount> findByDeletedAtIsNotNull();

    // Boolean predicates
    List<UserAccount> findByEnabledTrue();

    List<UserAccount> findByEnabledFalse();

    List<UserAccount> findByEnabledIsNull();

    List<UserAccount> findByVerifiedTrue();

    List<UserAccount> findByVerifiedFalse();

    // Combining boolean and null
    List<UserAccount> findByEnabledFalseOrEnabledIsNull();

    List<UserAccount> findByVerifiedTrueAndEnabledFalse();

    // Subjects other than find
    long countByDeletedAtIsNull();

    boolean existsByEmailIsNotNull();
}
```

Method names are parsed when Spring builds repository queries. If a property name or keyword is invalid, the application may fail at startup or when creating the query depending on configuration.

## 7. Combining IsNull/IsNotNull with True/False and Other Keywords

Derived queries allow chaining multiple conditions with `And` and `Or`.

### 7.1. Using And

For example, finding enabled, verified accounts that have not been soft-deleted:

```java
List<UserAccount>
findByEnabledTrueAndVerifiedTrueAndDeletedAtIsNull();
```

Semantically equivalent SQL:

```sql
SELECT *
FROM user_accounts
WHERE enabled = TRUE
  AND verified = TRUE
  AND deleted_at IS NULL;
```

A row is returned only when all conditions evaluate to TRUE. Rows where `enabled`, `verified`, or `deleted_at` is NULL will not satisfy the corresponding predicate.

### 7.2. Using Or

Finding accounts that are disabled or do not yet have a verification timestamp:

```java
List<UserAccount>
findByEnabledFalseOrVerifiedAtIsNull();
```

In this example, `verifiedAt` must be a property on the domain class mapped to the corresponding column.

Equivalent SQL:

```sql
SELECT *
FROM user_accounts
WHERE enabled = FALSE
   OR verified_at IS NULL;
```

`Or` means only one predicate branch needs to be true. If one branch returns UNKNOWN due to NULL, the other branch can still make the whole expression TRUE.

### 7.3. Combining And and Or

Method names containing both `And` and `Or` must be read carefully. Query derivation splits predicates into OR branches, where each branch may contain multiple AND conditions. Do not write a very long method name and rely on human intuition to guess grouping order.

For example, if you want to express:

```sql
WHERE (enabled = TRUE AND deleted_at IS NULL)
   OR (enabled = FALSE AND verified IS NULL)
```

name the method carefully and verify the generated query, or use explicit `@Query` SQL if the expression needs complex grouping. Derived method names are not a convenient place to express multi-level nested parentheses.

## 8. Combining with count, exists, and Result Types

The `IsNull`, `IsNotNull`, `True`, and `False` predicates are not limited to `find`.

### 8.1. Count

```java
long countByDeletedAtIsNull();

long countByEnabledTrue();

long countByEnabledFalse();
```

These methods return the number of rows satisfying the condition without loading the full list of objects.

### 8.2. Exists

```java
boolean existsByEmailIsNull();

boolean existsByEnabledTrue();
```

Use `exists` when you only need to know whether a matching record exists. It expresses intent more clearly than calling `find...` and checking whether the list is empty.

### 8.3. Optional and List

If the condition does not guarantee uniqueness, use `List<T>`:

```java
List<UserAccount> findByEnabledTrue();
```

Only use `Optional<T>` when the domain/schema guarantees at most one result:

```java
Optional<UserAccount> findById(Long id);
```

A method like `findByEmailIsNull()` can normally return multiple rows, so do not declare `Optional<UserAccount>` if multiple accounts are allowed to lack an email. If a repository query returns multiple rows when the method expects a single result, Spring Data may throw an incorrect result size error.

## 9. Primitive boolean vs. Wrapper Boolean

Java provides two commonly used types:

| Type | Representable values | Nullable? |
|---|---|---|
| `boolean` | `true`, `false` | No |
| `Boolean` | `Boolean.TRUE`, `Boolean.FALSE`, `null` | Yes |

If the database column allows NULL, the Java property should use `Boolean` when the application needs to preserve the unset state.

Example:

```java
private Boolean enabled;
```

When reading data, the property can be `null`. The repository can query that state using:

```java
List<UserAccount> findByEnabledIsNull();
```

If you use the primitive:

```java
private boolean enabled;
```

then the Java object cannot represent null. Design the schema with `NOT NULL` and an appropriate default if the domain only has two states: true and false. If an existing column is nullable while the domain uses a primitive, handle NULL data beforehand or define an appropriate mapping/conversion; do not let missing data silently turn into false by accident.

### 9.1. Null does not automatically become false

Do not assume that:

```java
Boolean enabled = null;
```

is equivalent to:

```java
Boolean enabled = false;
```

Those are two distinct states. If a business rule states that null should be treated as false, make that explicit in the query or migration:

```java
List<UserAccount> findByEnabledFalseOrEnabledIsNull();
```

Or update existing data to convert null to false and make the column `NOT NULL`, if that is the official rule.

## 10. Derived Query vs. @Query SQL

For simple conditions, derived methods are usually easy to read:

```java
List<UserAccount> findByDeletedAtIsNull();

List<UserAccount> findByEnabledTrue();
```

When you need database-specific SQL or complex expressions, Spring Data JDBC lets you declare `@Query` with SQL suited to your database.

Example:

```java
import org.springframework.data.jdbc.repository.query.Query;

@Query("""
    SELECT *
    FROM user_accounts
    WHERE deleted_at IS NULL
      AND enabled = TRUE
    """)
List<UserAccount> findActiveEnabledAccounts();
```

This is SQL, not JPQL. `@Query` in Spring Data JDBC must be written according to the dialect and schema your database uses. Java text block syntax requires a Java version that supports text blocks; if your project uses an older Java version, use regular string literals.

Use derived queries when:

- The predicate is simple and uses supported keywords.
- The method name stays short and easy to understand.
- No database-specific expression is required.

Use `@Query` when:

- Expressions are complex or require explicit parentheses.
- Joins, projections, or database-specific SQL are needed.
- The derived method name becomes long and hard to read.
- You want direct control over the executed SQL statement.

Do not use `@Query` just to replace a simple `IsNull` if a derived method already expresses the intent clearly.

## 11. Property Names, Column Names, and Reserved Words

A common mistake is using the column name instead of the property name in a method.

Domain example:

```java
@Column("deleted_at")
private LocalDateTime deletedAt;
```

Correct method:

```java
List<UserAccount> findByDeletedAtIsNull();
```

Do not write:

```java
List<UserAccount> findByDeleted_atIsNull();
```

Derived queries parse properties of the domain model, so use camelCase Java properties. `@Column` only controls mapping a property to an SQL column name.

If a property name is confusing or collides with a keyword, give the Java property a clear name and use `@Column` to map it to the required schema column name.

## 12. Testing Null and Boolean Conditions

Tests need data covering all three states of a nullable `Boolean`.

Example fixture:

| email | enabled | deleted_at | Meaning |
|---|---|---|---|
| a@example.com | TRUE | NULL | Enabled, not soft-deleted |
| b@example.com | FALSE | NULL | Disabled, not soft-deleted |
| NULL | NULL | NULL | No email and enabled unset |
| d@example.com | TRUE | timestamp | Soft-deleted |

Test with Spring Boot's JDBC slice:

```java
@DataJdbcTest
class UserAccountRepositoryTest {

    @Autowired
    UserAccountRepository accounts;

    @Test
    void distinguishesNullTrueAndFalse() {
        assertThat(accounts.findByEnabledTrue())
                .extracting(UserAccount::getEmail)
                .contains("a@example.com", "d@example.com");

        assertThat(accounts.findByEnabledFalse())
                .extracting(UserAccount::getEmail)
                .containsExactly("b@example.com");

        assertThat(accounts.findByEnabledIsNull())
                .hasSize(1);
    }

    @Test
    void findsSoftDeletedAndNotDeletedAccounts() {
        assertThat(accounts.findByDeletedAtIsNull())
                .hasSize(3);

        assertThat(accounts.findByDeletedAtIsNotNull())
                .hasSize(1);
    }
}
```

This test assumes the fixture has been inserted before the assertions run and the schema permits the corresponding NULL values. Test imports such as `@DataJdbcTest`, `@Autowired`, `@Test`, and AssertJ must be present in the project's test dependencies.

### 12.1. Inspecting SQL when needed

If results do not match expectations, inspect the executed SQL and the actual table data. You can enable JDBC logging in test/dev environments:

```properties
logging.level.org.springframework.jdbc.core=DEBUG
```

Logging output depends on your logger and Spring version. Do not enable sensitive logging in production if statements or parameters could contain personal data.

## 13. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| `findByEnabledFalse()` does not return rows with NULL enabled | False and NULL are different states | Use `findByEnabledFalseOrEnabledIsNull()` if business logic requires both |
| `findByEmailIsNotNull()` still returns empty strings | `IS NOT NULL` only checks for null | Add an empty/blank string check or validation |
| Method fails to parse | Wrong property name or keyword | Verify Java property and Spring Data supported keywords |
| Using column name in method causes query error | Derived queries require property names | Use camelCase property, not SQL column name |
| `findByEnabledTrue(Boolean value)` makes no sense | `True` keyword is a fixed predicate, no parameter needed | Use `findByEnabledTrue()` |
| `Optional` fails with multiple results | Null condition can match multiple rows | Use `List` or guarantee uniqueness |
| Nullable boolean loses null state | Domain uses primitive `boolean` or data was normalized | Use `Boolean` if three states are needed; handle migration |
| `Not` query does not return NULL | SQL `<>` evaluates to UNKNOWN on NULL | Add `OrPropertyIsNull` if null should be included |
| SQL boolean literals differ across databases | Dialect/column type differences | Use derived predicates or write DB-specific SQL |
| Tests have no NULL rows | Fixture or schema forbids NULL | Check DDL and test data |

## 14. Quick Reference Table

| Goal | Derived method | SQL semantics |
|---|---|---|
| Property is NULL | `findByPropertyIsNull()` | `property IS NULL` |
| Property is not NULL | `findByPropertyIsNotNull()` | `property IS NOT NULL` |
| Boolean property is true | `findByEnabledTrue()` | `enabled = TRUE` semantically |
| Boolean property is false | `findByEnabledFalse()` | `enabled = FALSE` semantically |
| Boolean property is null | `findByEnabledIsNull()` | `enabled IS NULL` |
| False or null | `findByEnabledFalseOrEnabledIsNull()` | `enabled = FALSE OR enabled IS NULL` |
| True and not soft-deleted | `findByEnabledTrueAndDeletedAtIsNull()` | `enabled = TRUE AND deleted_at IS NULL` |
| Count non-soft-deleted records | `countByDeletedAtIsNull()` | `COUNT` with `deleted_at IS NULL` |
| Check if any record has email | `existsByEmailIsNotNull()` | Existence check with `email IS NOT NULL` |

## 15. Principles to Remember

- **IsNull** and **IsNotNull** inspect the NULL state of a property; they do not compare against a parameter.
- **True** and **False** are fixed boolean predicates; you do not pass `true`/`false` to the method.
- For a nullable `Boolean` property, there are three states: `TRUE`, `FALSE`, and `NULL`. `findByEnabledFalse()` does not include NULL.
- SQL uses `IS NULL`/`IS NOT NULL`; do not use `= NULL`/`<> NULL`.
- `And` and `Or` can combine multiple predicates, but complex expressions should use explicit SQL to avoid misreading condition grouping.
- Derived methods use **Java property names**; `@Column` maps properties to database column names.
- Choose `List`, `Optional`, `count`, or `exists` based on result cardinality and query intent.

When using null and boolean conditions, start from the meaning of each data state in the domain. If NULL means "unknown" or "unset," keep it separate from FALSE. When business rules need to combine the two states, write an explicit `Or...IsNull` condition. Proper method naming lets Spring Data JDBC generate clear queries and helps anyone reading the repository understand the data semantics directly from code.
