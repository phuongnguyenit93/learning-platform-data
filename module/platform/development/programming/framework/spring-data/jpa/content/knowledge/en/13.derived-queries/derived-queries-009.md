# IgnoreCase, AllIgnoreCase, and Their Impact on Indexes

Spring Data JPA supports case-insensitive queries through the `IgnoreCase` and `AllIgnoreCase` keywords in repository method names. They are commonly used when searching names, emails, or text codes that users may enter with varying uppercase/lowercase letters.

Example:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);
~~~

This method requests a case-insensitive email comparison according to the query mechanism of the provider and database. However, this convenience can affect index usage. If the generated SQL applies functions like `UPPER()` or `LOWER()` to a column, a standard B-tree index on the original column may not be used effectively. Therefore, it is important to understand query syntax, database collation, and execution plans.

## 1. What is IgnoreCase?

`IgnoreCase` is a Spring Data query derivation keyword that requests case-insensitive comparison on a `String` property.

Entity example:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String firstName;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {
    }

    public Customer(String firstName, String email) {
        this.firstName = firstName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);
}
~~~

Given stored email `User@example.com`, querying for `user@EXAMPLE.COM` can find the same record when the database/provider executes a case-insensitive comparison under that mapping.

`IgnoreCase` applies to eligible text properties. It has no meaning for numeric, date/time, or boolean properties. Property names in the method must still match the Entity's Java properties.

## 2. How to write IgnoreCase in method names

`IgnoreCase` can be placed after the property to be compared:

~~~java
Optional<Customer> findByFirstNameIgnoreCase(String firstName);
~~~

It can be combined with other conditions:

~~~java
Optional<Customer> findByEmailIgnoreCaseAndId(
        String email,
        Long id
);
~~~

In this example, the email comparison is case-insensitive; the `id` comparison remains a normal numeric comparison.

`IgnoreCase` can be used with string operators such as:

~~~java
List<Customer> findByFirstNameContainingIgnoreCase(String keyword);

List<Customer> findByFirstNameStartingWithIgnoreCase(String prefix);

List<Customer> findByFirstNameEndingWithIgnoreCase(String suffix);
~~~

Meaning:

- `ContainingIgnoreCase`: case-insensitive substring search.
- `StartingWithIgnoreCase`: case-insensitive prefix search.
- `EndingWithIgnoreCase`: case-insensitive suffix search.

These methods typically correspond to LIKE comparisons with wildcards. Exact SQL representation depends on the Spring Data version, Hibernate, and database.

## 3. What is AllIgnoreCase?

`AllIgnoreCase` (also aliased as `AllIgnoringCase`) requests case-insensitive comparison for all eligible properties in the query method's predicate.

Example:

~~~java
List<Customer> findByFirstNameAndEmailAllIgnoreCase(
        String firstName,
        String email
);
~~~

Both `firstName` and `email` are compared case-insensitively.

Compare with specifying it per property:

~~~java
List<Customer> findByFirstNameIgnoreCaseAndEmailIgnoreCase(
        String firstName,
        String email
);
~~~

Both approaches express the same intent for eligible String properties.

### When to use IgnoreCase vs. AllIgnoreCase?

| Syntax | Scope |
|---|---|
| findByEmailIgnoreCase | Only email |
| findByFirstNameIgnoreCaseAndEmail | Only firstName |
| findByFirstNameAndEmailAllIgnoreCase | All eligible String properties in the predicate |
| findByFirstNameIgnoreCaseAndEmailIgnoreCase | Both fields explicitly specified |

`AllIgnoreCase` does not mean converting every data type to a string or ignoring case across the entire Entity. It applies to eligible properties, primarily String. Properties that do not support case-insensitive comparison are still processed according to their respective types and operators.

If a method has many conditions, read the method name carefully and verify the query derivation to be sure the scope of `IgnoreCase` matches what you intend. When a method name becomes long and hard to read, `@Query` can express conditions more clearly.

## 4. How might Spring Data JPA generate SQL?

To perform case-insensitive comparisons, providers commonly normalize both sides of the comparison using a function such as `UPPER()` or `LOWER()`.

Method example:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);
~~~

Illustrative SQL might look like:

~~~sql
SELECT c.*
FROM customers c
WHERE UPPER(c.email) = UPPER(?);
~~~

This is an illustrative SQL form, not a strict guarantee of the exact SQL generated across all versions/providers. Hibernate may choose `UPPER` or another representation depending on dialect and configuration.

For a substring query:

~~~java
List<Customer> findByFirstNameContainingIgnoreCase(String keyword);
~~~

SQL might look similar to:

~~~sql
SELECT c.*
FROM customers c
WHERE UPPER(c.first_name) LIKE UPPER(?);
~~~

The parameter is used alongside wildcards for substring matching. Enable SQL logging in development or use a datasource proxy to observe the actual SQL and bound values.

## 5. Why can IgnoreCase affect indexes?

Suppose the `customers` table has a regular B-tree index:

~~~sql
CREATE INDEX idx_customers_email
ON customers (email);
~~~

A direct comparison query:

~~~sql
SELECT *
FROM customers
WHERE email = ?;
~~~

can use the index on `email` if the query optimizer finds it beneficial.

However, an `IgnoreCase` query may be expressed as:

~~~sql
WHERE UPPER(email) = UPPER(?)
~~~

Here, the database must compare the result of the expression `UPPER(email)`. An index on the raw `email` values does not necessarily contain the transformed `UPPER()` values. Consequently, the regular index may not be used or may be ineffective for this condition.

Possible consequences:

- The database must evaluate the function across many rows.
- The execution plan may shift to scanning more data.
- CPU and I/O increase as the table grows.
- Query latency rises as record counts or search frequency increase.

Still, do not conclude that every `IgnoreCase` always causes a full table scan. The optimizer, collation, index type, statistics, and database engine can alter the choice. Inspect the actual execution plan.

## 6. Functional indexes or expression indexes

One solution is to create an index on the exact expression used in the query condition.

If actual SQL uses `UPPER(email)`, you can create an expression index on `UPPER(email)` in databases that support it:

~~~sql
CREATE INDEX idx_customers_email_upper
ON customers (UPPER(email));
~~~

When a query has a compatible condition:

~~~sql
WHERE UPPER(email) = UPPER(?)
~~~

the database can utilize this expression index.

The example above uses common syntax for PostgreSQL and some other databases supporting function-based/expression indexes. Exact syntax and support vary by database; consult your engine's documentation.

Points to watch:

- The expression in the index must match the expression in the query.
- If the provider emits `LOWER(email)` while the index was created on `UPPER(email)`, the database may not use that index.
- Changing dialects or providers can change the generated SQL.
- Expression indexes increase INSERT, UPDATE, and DELETE overhead because the database must maintain the index.
- If `email` changes frequently, weigh write overhead against search benefits.

Do not create an index merely because an `IgnoreCase` method exists. Measure the execution plan and workload first before deciding.

## 7. Case-insensitive collation

Another approach is using a collation or column type with case-insensitive comparison rules provided by the database.

Collation governs how strings are compared and sorted. Some databases support case-insensitive collations at the database, column, or expression level. When a column already uses a suitable collation, direct comparisons may not need `UPPER`/`LOWER` wrappers.

However:

- Collation is a database-specific feature, not a portable JPA feature.
- Collation names and syntax differ across PostgreSQL, MySQL, SQL Server, and other engines.
- Some collations also affect diacritics, Unicode characters, and sort order.
- Indexes must be created with a collation compatible with the comparison.
- Changing collations requires checking unique constraints and existing data.

If the database already performs case-insensitive comparisons via collation, evaluate whether `IgnoreCase` is still necessary. Avoid accidentally stacking multiple normalization layers that prevent index usage.

## 8. Storing normalized values in a separate column

Another strategy is storing both the original value and a normalized value for searching.

Example:

- `email`: preserves the casing provided by the user.
- `normalizedEmail`: stores the email normalized according to business rules.
- Create a unique index or regular index on `normalizedEmail`.
- On write, update both fields using the same rule.
- On search, compare `normalizedEmail` directly with the normalized input value.

Entity:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false, unique = true)
    private String normalizedEmail;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
        this.normalizedEmail = normalizeEmail(email);
    }

    private static String normalizeEmail(String value) {
        return value.trim().toLowerCase(Locale.ROOT);
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByNormalizedEmail(String normalizedEmail);
}
~~~

The service can normalize input using the exact same rule before calling the Repository.

Note: this example illustrates a simple normalization rule. Email addresses have specific comparison rules regarding the domain vs. the local-part; do not blindly lowercase every email address if the system must comply with full email semantics. Clearly define canonicalization rules for business data and apply them consistently on create, update, import, and search.

Advantages of a normalized column:

- Queries can use a standard B-tree index on the normalized column.
- Normalization rules are explicit in the application layer.
- A case-insensitive unique constraint can be enforced according to the chosen rule.

Disadvantages:

- Both values must be kept in sync.
- Migrations are needed to backfill legacy data.
- Every write path must apply the same rule.
- Uses extra storage and carries a risk of original and normalized data drifting out of sync.

## 9. IgnoreCase and substring searching

Not all forms of case-insensitive search have the same index cost.

| Method | Common condition pattern | Standard B-tree usability |
|---|---|---|
| findByNameIgnoreCase | UPPER(name) = UPPER(?) | Original column may not suit; expression index can help |
| findByNameStartingWithIgnoreCase | UPPER(name) LIKE UPPER('abc%') | May use an index under certain conditions/dialects |
| findByNameEndingWithIgnoreCase | UPPER(name) LIKE UPPER('%abc') | Usually hard for B-tree |
| findByNameContainingIgnoreCase | UPPER(name) LIKE UPPER('%abc%') | Usually unsuitable for standard B-tree |

Leading wildcards such as `%abc` or `%abc%` make B-tree lookups difficult because the database cannot locate a contiguous prefix range in the usual way.

In PostgreSQL, substring searches may require specialized extensions/indexes such as `pg_trgm` with GIN/GiST. In other databases, full-text search, computed columns, collations, or dedicated search engines may be used. These are database-specific choices and are not automatically provided by `IgnoreCase` alone.

If search requirements are complex, clarify:
- Exact match or partial match?
- Does Vietnamese accent-insensitive search need to be supported?
- Do whitespace or Unicode characters need normalization?
- Prefix search or substring match at any position?
- What are the data volume and concurrency levels?

`IgnoreCase` only handles uppercase/lowercase differences according to provider/database behavior. It does not automatically strip accents, strip punctuation, normalize whitespace, or handle every Unicode variant.

## 10. Distinguishing case-insensitive search from uniqueness

Case-insensitive searching and case-insensitive uniqueness are two separate requirements.

For example, an application may want:

- Searching for `EMAIL@example.com` and `email@example.com` to return the same customer.
- Disallowing two accounts from having the same email under case-insensitive comparison.

Simply having the method:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);
~~~

does not guarantee the database prevents duplicates. Two concurrent transactions can both check that an email does not exist and then both insert values differing only in case.

To guarantee uniqueness, you need a database constraint/index using the same normalization rule or collation. For instance, if using a `normalizedEmail` column, create a unique index on that column. The application must still handle unique constraint violation errors because pre-insert checks do not eliminate race conditions.

## 11. Checking execution plans and actual SQL

On small tables, performance differences may not be obvious. On larger datasets, inspect the query plan.

Workflow:

1. Enable SQL logging in development to see whether Hibernate generates `UPPER()`, `LOWER()`, or a collation expression.
2. Verify bound values and JDBC types.
3. Run `EXPLAIN` or the database's execution plan tool.
4. Check whether the database uses an index or performs a scan.
5. Measure latency with production-scale data.
6. Compare before and after adding an expression index or normalized column.
7. Check write overhead and index storage size as well.

Do not rely solely on SQL logs to judge performance. The same SQL statement can produce different execution plans depending on statistics, data distribution, parameters, database version, and optimizer settings.

## 12. Testing IgnoreCase behavior on the target database

A basic repository test:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsEmailIgnoringCase() {
        repository.save(
                new Customer("User@example.com")
        );

        Optional<Customer> result =
                repository.findByEmailIgnoreCase(
                        "user@EXAMPLE.COM"
                );

        assertTrue(result.isPresent());
    }
}
~~~

The test above demonstrates functional intent, but to verify true production behavior, run against the same database engine and collation used in deployment. H2 may differ from PostgreSQL or MySQL in collation, Unicode handling, and expression optimization.

If the application uses an expression index or normalized column, integration tests should also verify:
- Queries return accurate results across case variants.
- Unique constraints reject duplicates under the rule.
- Migrations create the expected index/column.
- Query plans use the index when workload is large enough and the optimizer deems it beneficial.

## 13. Common mistakes

**Using IgnoreCase and assuming the regular index is still used**

If SQL wraps the column in `UPPER`/`LOWER`, an index on the raw value may not match. Inspect the query plan and consider an expression index, collation, or normalized column.

**Mistaking AllIgnoreCase for ignoring differences across all properties**

`AllIgnoreCase` applies to eligible properties, mainly String, in the predicate; it does not turn numbers, dates, or booleans into case-insensitive comparisons.

**Checking duplicates only in the application layer**

Two concurrent transactions can slip past a pre-insert check. Enforce a unique constraint/index in the database matching the normalization rule.

**Inconsistent normalization**

If writes use lowercase while searches use different trimming or Unicode normalization, records can be missed. Create a single normalization function and use it on all write and read paths.

**Ignoring Unicode and collation**

`String.toLowerCase()` with the default locale can produce different results depending on the environment. When normalizing in Java, specify locale and semantics clearly; `Locale.ROOT` is usually better for language-independent technical rules, though it does not fully replace database collation.

**Using ContainingIgnoreCase on very large tables without a search strategy**

Substring searches with wildcards on both sides generally do not leverage regular B-tree indexes. Choose full-text, trigram, or a specialized database search mechanism.

## 14. Conclusion

`IgnoreCase` and `AllIgnoreCase` let Spring Data JPA generate case-insensitive text comparison queries. `IgnoreCase` applies to a specified property; `AllIgnoreCase` applies to all eligible properties in the predicate. Implementations commonly use `UPPER`/`LOWER` or rely on collation, which can impact index usage. For large tables, inspect SQL and execution plans, then consider expression indexes, case-insensitive collations, or normalized columns with unique constraints. `IgnoreCase` does not automatically handle accent-insensitive search, Unicode normalization, or data uniqueness.