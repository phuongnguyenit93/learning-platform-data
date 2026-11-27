# Wildcards, Escaping, and Differences When Passing Null in Spring Data JPA Queries

When searching by name, applications often need to support partial string matching, such as finding all customers whose name contains "An". In SQL and JPQL, the LIKE operator uses two important wildcards: the percent sign (%) matches zero or more characters, while the underscore (_) matches exactly one character. Users might want to search for the literal % or _ characters themselves, whereas the database interprets them as pattern wildcards.

Another issue is null values. Comparing against null in SQL does not behave like comparing against a regular value. Spring Data JPA has specific rules for derived queries, whereas `@Query` queries must express null handling explicitly. This lesson explains LIKE, escaping, null, empty strings, how to write safe repositories, and how to test boundary cases.

## 1. LIKE and the two standard wildcards

LIKE uses a pattern to match strings:

- % matches zero, one, or more characters.
- _ matches exactly one character.
- ESCAPE specifies a character used to disable the wildcard meaning of % or _ in the pattern.

Example with a name column:

| Condition | Example matching values | Explanation |
|---|---|---|
| name LIKE 'An%' | An, Anh, Anna | Starts with An |
| name LIKE '%An' | An, Minh An | Ends with An |
| name LIKE '%An%' | An, Thanh An, An Nguyen | Contains An |
| name LIKE 'A_' | An, Ax | A followed by exactly one character |
| name LIKE 'A__' | Anh, Amy | A followed by exactly two characters |

A LIKE pattern can contain wildcards in any position. For example, `'%a_b%'` finds strings with the letter a, followed by any single character, followed by b.

LIKE does not automatically mean case-insensitive search. That depends on database collation or how the query is written. Spring Data JPA provides the IgnoreCase suffix for derived queries; with `@Query`, you can use `lower()` or `upper()` when explicit rules are needed.

## 2. What is wildcard escaping?

Suppose a user enters the search term "A%". If the query builds the pattern `'%A%%'`, the % entered by the user is interpreted as a wildcard and may match many unintended names. If the goal is to find strings containing the literal percent character, you need to escape %.

SQL example using an exclamation mark as the escape character:

~~~sql
SELECT *
FROM customers
WHERE name LIKE '%A!%%' ESCAPE '!';
~~~

The ! before % causes that % to be treated as an ordinary character. The two % characters at the beginning and end remain wildcards added by the application.

Similarly, if you want to search for an underscore:

~~~sql
SELECT *
FROM customers
WHERE name LIKE '%A!_%' ESCAPE '!';
~~~

Escape character literal syntax can differ across SQL, Java strings, and database configurations. The examples above illustrate SQL semantics; when writing them in Java, also mind Java string literal escaping rules.

## 3. Spring Data JPA derived queries and LIKE

Spring Data JPA supports keywords that generate LIKE queries from method names:

| Keyword | Meaning | Example |
|---|---|---|
| Containing / Contains | Find substring | findByNameContaining |
| StartingWith | Find string starting with value | findByNameStartingWith |
| EndingWith | Find string ending with value | findByNameEndingWith |
| Like | Use passed LIKE pattern | findByNameLike |
| NotLike | Negate LIKE pattern | findByNameNotLike |
| IgnoreCase | Case-insensitive comparison | findByNameContainingIgnoreCase |

Repository example:

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByName(String name);

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    List<Customer> findByNameLike(String pattern);
}
~~~

With Containing, StartingWith, and EndingWith, Spring Data automatically adds the required wildcards to the parameter. Example:

~~~java
repository.findByNameContaining("Lan");
repository.findByNameStartingWith("Ng");
repository.findByNameEndingWith("Anh");
~~~

The framework constructs LIKE patterns for containing, starting with, or ending with the passed value. You do not need to manually add % to the parameter for these three methods.

An important feature of derived LIKE queries is that Spring Data JPA escapes standard wildcards passed by the user in the parameter, so % and _ in the search value are treated literally. The escape character is configured for the repository. Therefore, Containing methods are usually appropriate when users want to find an exact text fragment, even if that fragment contains % or _.

Conversely, methods ending with Like accept a LIKE pattern. When using Like, the application is intentionally passing a query pattern; decide clearly whether wildcards in the parameter should have search semantics or need escaping.

## 4. Difference between Containing and Like

The following two methods have different meanings:

~~~java
List<Customer> findByNameContaining(String text);

List<Customer> findByNameLike(String pattern);
~~~

Containing automatically creates a substring search pattern and escapes standard wildcards in the input value. For example, passing "A%" means finding names containing the two literal characters A and %.

Like uses the pattern supplied by the application. Example:

~~~java
repository.findByNameLike("A%");
~~~

The pattern "A%" means names starting with A followed by zero or more characters. If you want to match a literal % character, construct an escaped pattern using the ESCAPE character used by the query.

Do not manually add % to a Containing parameter:

~~~java
// Avoid: Containing already adds wildcards on both sides.
repository.findByNameContaining("%Lan%");
~~~

User-entered % signs are treated as literal characters under derived query rules, while the framework still adds the outer wildcards. If you want to pass a complete LIKE pattern, use a Like method and handle escaping explicitly.

## 5. Configuring the escape character for repositories

Spring Data JPA lets you configure the escape character in `@EnableJpaRepositories` via the `escapeCharacter` attribute. The default character is the backslash.

You can explicitly configure another character, such as an exclamation mark:

~~~java
package com.example.customer;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(escapeCharacter = '!')
public class RepositoryConfiguration {
}
~~~

Normally, there is no need to reconfigure it if the default meets your requirements. Only change it when the project follows a unified escaping convention or needs to avoid conflicts with input data. The chosen character must be compatible with the database's ESCAPE clause.

## 6. Writing @Query with LIKE and safe escaping

When using `@Query`, you define the LIKE pattern yourself. If you add wildcards without escaping the data, % and _ inside the parameter can alter the search meaning.

Spring Data JPA provides the SpEL `escape(String)` function in queries to escape the two standard SQL/JPQL wildcards % and _. The `escapeCharacter()` function returns the escape character configured for the repository.

Example finding names containing the literal input fragment:

~~~java
@Query("""
       select c
       from Customer c
       where c.name like %?#{escape([0])}% escape ?#{escapeCharacter()}
       """)
List<Customer> findNameContainingLiteral(String fragment);
~~~

How it works:

1. `[0]` is the first method parameter.
2. `escape([0])` escapes standard wildcards % and _ in the user value.
3. The two `%` signs outside the SpEL expression are added by the application for substring matching.
4. `escapeCharacter()` supplies the character used in the ESCAPE clause.

Spring Data's `escape` function only handles standard SQL/JPQL wildcards % and _. It does not handle all database-specific special characters. If your database has additional pattern syntax, consult the database documentation and design appropriate rules.

You can combine IgnoreCase using `lower()`:

~~~java
@Query("""
       select c
       from Customer c
       where lower(c.name)
             like lower(concat('%', ?#{escape([0])}, '%'))
             escape ?#{escapeCharacter()}
       """)
List<Customer> findNameContainingIgnoreCaseLiteral(String fragment);
~~~

The query uses `concat` to add application-controlled wildcards; the parameter value is escaped before being inserted into the pattern.

Do not concatenate user data directly into JPQL or SQL. Use parameter binding and proper escaping mechanisms. Parameter binding protects against SQL injection; wildcard escaping solves a different problem, namely LIKE pattern semantics. Both must be understood properly.

Additional note: the `escape()` function is designed to handle standard wildcards % and _, not every database-specific special character. If users can enter the chosen escape character itself, test and define how that character should be handled; do not assume `escape()` covers all special cases.

## 7. Null in SQL and JPQL

SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. When comparing a value to NULL using `=` or `<>`, the result is UNKNOWN, not TRUE or FALSE.

Example:

~~~sql
SELECT *
FROM customers
WHERE name = NULL;
~~~

This query will not find rows where name is NULL. The correct way is:

~~~sql
SELECT *
FROM customers
WHERE name IS NULL;
~~~

Similarly:

~~~sql
SELECT *
FROM customers
WHERE name IS NOT NULL;
~~~

In JPQL, the same rule applies:

~~~java
select c from Customer c where c.name is null
~~~

~~~java
select c from Customer c where c.name is not null
~~~

Therefore, do not write `name = :name` expecting passing null to automatically turn into `IS NULL` in every query type. Distinguish between derived queries generated by Spring Data and JPQL you write yourself.

## 8. Passing null to derived queries

For derived queries using equality comparisons, Spring Data JPA interprets a null parameter as an `IS NULL` condition.

Example:

~~~java
Optional<Customer> findByName(String name);
~~~

When calling:

~~~java
repository.findByName(null);
~~~

The generated condition corresponds to `name IS NULL`. This differs from hand-written JPQL with `name = :name`, where binding null remains an equality comparison against null under SQL logic and does not return null rows.

To express intent explicitly, declare dedicated methods:

~~~java
List<Customer> findByNameIsNull();

List<Customer> findByNameIsNotNull();
~~~

These methods are easy to read and do not depend on the caller remembering to pass null.

Do not generalize this rule to all query keywords. LIKE, Containing, Between, greater/less-than comparisons, and `@Query` queries handle parameters differently. Whenever a parameter may be null, define behavior explicitly and test on your Spring Data JPA version.

## 9. Passing null to @Query

Consider this JPQL:

~~~java
@Query("select c from Customer c where c.name = :name")
List<Customer> searchExact(@Param("name") String name);
~~~

If you call `searchExact(null)`, the query still has an equality condition against a null parameter. In SQL, `name = NULL` evaluates to UNKNOWN, so rows with `name IS NULL` are not returned.

If you want a null parameter to mean finding records with a null name, write both branches explicitly:

~~~java
@Query("""
       select c
       from Customer c
       where (:name is null and c.name is null)
          or c.name = :name
       """)
List<Customer> searchExactOrNull(@Param("name") String name);
~~~

If the goal is simply "when the parameter is null, skip the filter", use:

~~~java
@Query("""
       select c
       from Customer c
       where (:name is null or c.name = :name)
       """)
List<Customer> searchOptionalName(@Param("name") String name);
~~~

The two queries have different meanings:

- `searchExactOrNull(null)` retrieves only rows where name is null.
- `searchOptionalName(null)` applies no name filter and can return all customers.

Do not confuse "null means find null values" with "null means do not filter this field". These are two separate business rules.

## 10. Null in LIKE queries

LIKE NULL does not return TRUE. Example:

~~~sql
SELECT *
FROM customers
WHERE name LIKE NULL;
~~~

The condition evaluates to UNKNOWN and returns zero rows.

In a derived query like `findByNameContaining(fragment)`, do not assume passing null will automatically match null columns or skip the filter. Handle null parameters in the service or use a separate `IsNull` method if the goal is finding null values.

Example of a service making an explicit decision:

~~~java
public List<Customer> searchByName(String fragment) {
    if (fragment == null) {
        return repository.findAll();
    }

    if (fragment.isBlank()) {
        return List.of();
    }

    return repository.findByNameContainingIgnoreCase(fragment.trim());
}
~~~

This is just one illustrative policy. Another API might define null as finding null names or returning a validation error. What matters is that the decision is explicit and consistent.

## 11. Null, empty strings, and whitespace-only strings

These three values are different:

| Input value | Meaning | Handling to decide |
|---|---|---|
| null | No value provided | Skip filter, query IS NULL, or report error |
| "" | Zero-length string | Search for empty string or treat as no input |
| "   " | Whitespace string | Keep as-is, trim, or reject |

Examples:

- `findByName(null)` with derived equality can find `name IS NULL`.
- `findByName("")` finds empty string values.
- `findByNameContaining("")` creates a substring search for the empty string; the LIKE pattern can match every non-null name value.
- `findByNameContaining("   ")` searches for fragments containing spaces, unless the service trims or validation rejects it.

Do not automatically treat null, empty, and blank as the same. If the UI sends an empty string when the user leaves a search box blank, the service should normalize according to the API contract.

Normalization example:

~~~java
private String normalizeSearchText(String value) {
    if (value == null) {
        return null;
    }

    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
}
~~~

Then the service can treat null after normalization as "no filter". Document this policy clearly in the API contract and tests.

## 12. Optional filter pattern for multiple fields

A search screen may have multiple optional parameters. You can use null-parameter checks or conditional predicates:

~~~java
@Query("""
       select c
       from Customer c
       where (:name is null or lower(c.name) like lower(concat('%', :name, '%')))
         and (:email is null or lower(c.email) = lower(:email))
       """)
Page<Customer> search(
        @Param("name") String name,
        @Param("email") String email,
        Pageable pageable);
~~~

This approach is simple when there are few filters. However, keep in mind:

- If name can contain % or _, the LIKE query must escape them if literal matching is desired.
- null here means skipping the corresponding condition.
- An empty string is still non-null and can produce a `%%` pattern.
- Multiple OR branches can make it hard for the database to use indexes.
- The count query for Page can be costly when there are many optional conditions.

When filters become complex, consider building dynamic queries with Specification, Criteria API, or Querydsl. Adding predicates only for parameters that actually have values makes the intent clearer and can produce better SQL.

## 13. Derived queries vs @Query in edge cases

| Need | Derived query | @Query |
|---|---|---|
| Exact name lookup | findByName | JPQL name = :name |
| Find null names | findByNameIsNull | JPQL name is null |
| Find non-null names | findByNameIsNotNull | JPQL name is not null |
| Literal substring search | findByNameContaining | @Query with escape() |
| Active wildcard pattern search | findByNameLike | JPQL LIKE with pattern |
| Null parameter means skip filter | Handle in service or separate method | (:name is null or ...) |
| Multiple dynamic filters | Multiple methods or Specification | JPQL with multiple optional conditions |

Derived queries work well when conditions are simple and method names remain readable. `@Query` works well when explicit control over LIKE expressions, escaping, joins, projections, or null logic is required.

Avoid creating overly long method names to describe multiple optional filter branches. When conditions grow complex, use Specification or dynamic queries.

## 14. Entity and repository example for practice

Minimal Customer entity:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "name", length = 150)
    private String name;

    @Column(name = "email", length = 200)
    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository combining equality, null, LIKE, and `@Query`:

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByName(String name);

    List<Customer> findByNameIsNull();

    List<Customer> findByNameIsNotNull();

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    List<Customer> findByNameLike(String pattern);

    @Query("""
           select c
           from Customer c
           where c.name like %?#{escape([0])}% escape ?#{escapeCharacter()}
           """)
    List<Customer> findNameContainingLiteral(String fragment);

    @Query("""
           select c
           from Customer c
           where (:name is null or c.name = :name)
           """)
    List<Customer> findByOptionalName(@Param("name") String name);
}
~~~

These methods illustrate different semantics. In real projects, keep only the methods required for actual use cases so the repository does not become a list of unused queries.

## 15. Testing wildcards and null with @DataJpaTest

Test special values to verify that framework and database behavior matches the contract.

~~~java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void containingTreatsWildcardsAsLiteralCharacters() {
        repository.save(new Customer("A%lice", "percent@example.com"));
        repository.save(new Customer("Alice", "alice@example.com"));
        repository.save(new Customer("A_lice", "underscore@example.com"));

        var percentMatches = repository.findByNameContaining("%");
        var underscoreMatches = repository.findByNameContaining("_");

        assertThat(percentMatches)
                .extracting(Customer::getName)
                .containsExactly("A%lice");

        assertThat(underscoreMatches)
                .extracting(Customer::getName)
                .containsExactly("A_lice");
    }

    @Test
    void equalityDerivedQueryWithNullFindsNullName() {
        repository.save(new Customer(null, "missing-name@example.com"));
        repository.save(new Customer("An", "an@example.com"));

        var result = repository.findByName(null);

        assertThat(result).isPresent();
        assertThat(result.get().getEmail())
                .isEqualTo("missing-name@example.com");
    }

    @Test
    void explicitNullQueryCanMeanNoFilter() {
        repository.save(new Customer(null, "null@example.com"));
        repository.save(new Customer("An", "an@example.com"));

        var result = repository.findByOptionalName(null);

        assertThat(result).hasSize(2);
    }
}
~~~

The first test verifies that derived Containing escapes standard wildcards. The second test checks null in derived equality. The third test demonstrates a `@Query` contract where null means skipping the filter.

If database collation or LIKE configuration differs, case sensitivity or character rules may vary. Run integration tests on the production database when the application depends on specific behavior.

## 16. Performance and security notes

LIKE with a leading wildcard, such as `'%term%'`, usually cannot leverage a standard B-tree index. For large tables, consider full-text search, trigram indexes, or database-appropriate search mechanisms.

Some guidelines:

- Prefix search with `'term%'` is generally more index-friendly than `'%term%'`.
- `lower(column)` can prevent a regular index from being used unless an appropriate functional index exists.
- IgnoreCase may generate `lower()` expressions or provider-specific handling.
- Choose an appropriate collation if you want case-insensitive comparison rules at the database level.
- Use bound parameters; do not concatenate input strings into JPQL/SQL.
- Escape wildcards when users intend literal search.
- Allow active wildcards only when the search feature requires them.
- Limit search string lengths and paginate results.
- Inspect execution plans on production-sized data.

SQL injection and wildcard injection are two distinct problems. Parameter binding protects statement structure; LIKE escaping protects wildcard semantics in search values.

## 17. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Searching '%' returns too many rows | % is interpreted as a wildcard | Use derived Containing or escape in @Query |
| Searching '_' matches arbitrary characters | _ matches any single character | Escape _ if searching for the literal character |
| Like and Containing produce different results | Like takes a pattern; Containing adds wildcards and escapes arguments | Pick the right method for the intent |
| Passing null to name = :name misses null rows | SQL equality with NULL evaluates to UNKNOWN | Use IS NULL or explicit conditional branches |
| Null skips filter unexpectedly | Query uses (:param is null or ...) | Define clearly whether null means skip filter or find null |
| Empty string returns too many results | Substring pattern can become %% | Normalize blank values or validate before querying |
| IgnoreCase still shows accent/locale differences | lower() and collation have their own rules | Check collation and normalize data |
| Query is slow with %term% | Leading wildcard makes standard indexes ineffective | Use full-text/trigram or suitable index design |
| SpEL escape misses DB-specific wildcards | escape() only handles standard % and _ | Check database documentation and add custom rules |

## 18. Self-assessment checklist

- [ ] Can explain % and _ in LIKE.
- [ ] Know how the ESCAPE clause is used to search literal wildcard characters.
- [ ] Distinguish Containing, StartingWith, EndingWith, and Like.
- [ ] Understand that Spring Data derived LIKE queries escape standard wildcards in parameters.
- [ ] Know how to configure escapeCharacter when needed.
- [ ] Use SpEL escape() and escapeCharacter() in @Query.
- [ ] Distinguish parameter binding from wildcard escaping.
- [ ] Can explain why column = NULL is not equivalent to column IS NULL.
- [ ] Know that null in derived equality is handled as IS NULL.
- [ ] Avoid generalizing the null rule to LIKE and all @Query statements.
- [ ] Distinguish null, empty strings, and whitespace-only strings.
- [ ] Design optional filters with explicit null semantics.
- [ ] Write tests for %, _, null, and empty strings.
- [ ] Know how to evaluate indexes and performance of LIKE searches.

## 19. Conclusion

LIKE uses % and _ as wildcards. When users want to search for those literal characters, they must be escaped. Spring Data JPA derived queries like Containing automatically handle standard wildcards in parameters; with `@Query`, use parameter binding alongside `escape()` and `escapeCharacter()` or build tested ESCAPE rules yourself.

Null must also be defined intentionally. Derived equality can translate a null parameter into IS NULL, whereas JPQL `field = :value` does not automatically convert to IS NULL. For optional filters, decide whether null means skip the filter, match null values, or report an error. Clearly distinguishing null, empty, and blank keeps queries predictable, safe, and aligned with business logic.