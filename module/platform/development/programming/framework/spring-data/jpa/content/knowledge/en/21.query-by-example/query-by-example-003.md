# String Matching, Case Sensitivity, and NULL Values

When querying text data with Spring Data JPA, you need to clearly define whether the application wants exact matching, substring matching, prefix matching, or case-insensitive matching. JPQL provides string operators and functions such as LIKE, LOWER, UPPER, TRIM, CONCAT, and LOCATE. However, results are also affected by database collation, Unicode rules, and how NULL values are handled.

NULL is a special case: comparing against NULL with =, <>, LIKE, or NOT LIKE does not return TRUE, but evaluates to UNKNOWN. Therefore, IS NULL or IS NOT NULL must be used when checking for missing values. This lesson covers choosing matching modes, writing derived queries and JPQL, escaping wildcard characters safely, distinguishing null from empty strings, and testing behavior on the target database.

## 1. Common string matching types

A search requirement can carry several meanings:

| Requirement | Example with name | Commonly used query approach |
|---|---|---|
| Exact match | An matches only An | = |
| Starts with | An, Anh, Anny | LIKE 'An%' |
| Ends with | Minh An, Tuan An | LIKE '%An' |
| Contains substring | Hoang An, An Binh | LIKE '%An%' |
| Case-insensitive | an, An, AN | LOWER/UPPER or IgnoreCase |
| Missing value | name is NULL | IS NULL |
| Has value | name is not NULL | IS NOT NULL |

Before writing a query, align on the business meaning. Exact search differs from approximate search; substring search differs from prefix search; ignoring case differs from ignoring Vietnamese diacritics.

## 2. Exact matching with equals

JPQL uses = to compare two values:

~~~java
@Query("""
    select c
    from Customer c
    where c.email = :email
    """)
Optional<Customer> findByExactEmail(
    @Param("email") String email
);
~~~

This condition requires the email value to match according to the database's comparison rules and column type. Whether it is case-sensitive or not may depend on collation.

With derived queries, Spring Data can generate the query from the method name:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Use exact comparison when looking up codes, emails, or identifiers where business rules require matching the entire value. Do not use LIKE just to avoid handling whitespace or letter casing; define explicit normalization rules instead.

## 3. LIKE and the two wildcard characters

LIKE uses string patterns for matching:

- The percent sign (%) represents zero or more characters.
- The underscore (_) represents exactly one character.

Examples:

~~~sql
-- Starts with An
WHERE name LIKE 'An%'

-- Ends with An
WHERE name LIKE '%An'

-- Contains An anywhere
WHERE name LIKE '%An%'

-- An followed by exactly one character
WHERE name LIKE 'An_'
~~~

JPQL also uses LIKE:

~~~jpql
select c
from Customer c
where c.name like :pattern
~~~

If pattern is passed as An%, the query finds names starting with An. If %An% is passed, the query finds names containing An at any position.

LIKE does not automatically mean case-insensitive. That depends on collation and the database. To specify it explicitly, use LOWER/UPPER or an appropriate collation.

## 4. Derived queries with Containing, StartingWith, and EndingWith

Spring Data JPA supports keywords that generate LIKE patterns from method names:

~~~java
List<Customer> findByNameContaining(String fragment);

List<Customer> findByNameStartingWith(String prefix);

List<Customer> findByNameEndingWith(String suffix);

List<Customer> findByNameLike(String pattern);
~~~

Meaning:

- Containing adds wildcards on both sides of the parameter.
- StartingWith adds a wildcard at the end.
- EndingWith adds a wildcard at the beginning.
- Like accepts a pattern supplied by the caller.

Examples:

~~~java
repository.findByNameContaining("An");
repository.findByNameStartingWith("An");
repository.findByNameEndingWith("An");
repository.findByNameLike("An%");
~~~

The first methods express substring, prefix, and suffix intent. With Like, the caller is responsible for providing the proper wildcards.

Spring Data JPA includes a mechanism to escape wildcard characters in arguments to certain LIKE-based derived queries such as Containing, StartingWith, and EndingWith, so user-entered % or _ characters are treated as literal characters to search for rather than wildcards. The escape character can be configured in @EnableJpaRepositories depending on the Spring Data version in use. If using a manual @Query, design and test the escape rules yourself.

## 5. Case-insensitivity with IgnoreCase

Spring Data supports the IgnoreCase keyword for derived queries:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);

List<Customer> findByNameContainingIgnoreCase(String fragment);

List<Customer> findByNameStartingWithIgnoreCase(String prefix);
~~~

IgnoreCase requests case-insensitive string comparison. Spring Data JPA typically expresses this using the UPPER function on both the property and the parameter in the generated query.

For example, under a case-insensitive policy, An, AN, and an may be treated as equivalent during search.

IgnoreCase is only appropriate for string properties. Do not apply it to numbers, dates, or non-String types.

Do not assume IgnoreCase also ignores diacritics. Case-insensitive comparison and accent-insensitive comparison are two different requirements.

## 6. Using LOWER or UPPER in JPQL

If writing @Query, you can apply LOWER or UPPER on both sides:

~~~java
@Query("""
    select c
    from Customer c
    where lower(c.email) = lower(:email)
    """)
Optional<Customer> findByEmailCaseInsensitive(
    @Param("email") String email
);
~~~

Case-insensitive substring search:

~~~java
@Query("""
    select c
    from Customer c
    where lower(c.name) like lower(concat('%', :keyword, '%'))
    """)
List<Customer> searchNameIgnoreCase(
    @Param("keyword") String keyword
);
~~~

LOWER converts strings to lowercase according to database rules. UPPER converts to uppercase. Applying the same function to both sides makes comparisons independent of user input casing in many cases.

This is a common and readable approach, though it does not guarantee identical results across all Unicode languages on every database. LOWER/UPPER functions run in the database and do not necessarily follow exact Java locale rules.

If strict multilingual search is required, test special characters and configure an appropriate collation.

## 7. Distinguishing case-insensitive and accent-insensitive

Case-insensitive means An and an are treated as equivalent under comparison rules.

Accent-insensitive means forms like a and á can be treated as equivalent. This is a different policy.

LOWER and UPPER only change letter case according to case conversion rules; they are not accent-stripping functions. Thus, lower(name) does not automatically turn Nguyễn into Nguyen.

To support accent-insensitive search, you may need:

- An accent-insensitive database collation.
- A database-specific function or extension.
- A separate accent-normalized search column kept in sync.
- A suitable full-text search tool or search engine.

These solutions depend on the database or architecture. Do not assume standard JPQL has a portable function to strip Vietnamese diacritics.

## 8. Collation determines how the database compares strings

Collation governs many aspects of string comparison and sorting, such as:

- Whether comparisons are case-sensitive or not.
- Whether comparisons are accent-sensitive or not.
- Locale-specific comparison rules.
- Handling of certain Unicode characters.

For example, a column with a case-insensitive collation may consider An and an equal even when the query uses =. A column with a case-sensitive collation may distinguish them.

Default behavior varies across database engines, versions, database configurations, and per-column configurations. MySQL often uses collations tied to charset/column settings; PostgreSQL is typically case-sensitive for standard comparisons and offers the ILIKE extension; SQL Server depends on database or column collation. These are directional descriptions and do not replace checking your actual configuration.

Verify the collation of the target search column before concluding whether a query is case-sensitive.

## 9. User-entered wildcard characters

A common mistake is assuming bound parameters solve every issue with LIKE searches.

Bind parameters separate data from query structure, preventing direct concatenation of input into JPQL/SQL. However, if a user enters % or _, those two characters still act as wildcards in LIKE. Results may be broader than the user intended.

For example, a user searches for the code 50%OFF. If %50%OFF% is passed directly as the pattern, the % inside the search term can be interpreted as a wildcard rather than a literal percent sign.

If literal string matching is required, wildcard characters must be escaped.

## 10. Escaping wildcards in JPQL

JPQL LIKE supports the ESCAPE clause. For example, using an exclamation mark (!) as the escape character:

~~~jpql
select c
from Customer c
where c.name like :pattern escape '!'
~~~

Before binding, transform:

- ! to !!
- % to !%
- _ to !_

Only then add wildcards on both ends if doing a substring search.

Java example:

~~~java
public final class LikePattern {

    private LikePattern() {
    }

    public static String containsLiteral(String value) {
        String escaped = value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");

        return "%" + escaped + "%";
    }
}
~~~

Repository:

~~~java
@Query("""
    select c
    from Customer c
    where lower(c.name) like lower(:pattern) escape '!'
    """)
List<Customer> searchNameLiteral(
    @Param("pattern") String pattern
);
~~~

Service call:

~~~java
String pattern = LikePattern.containsLiteral(keyword);
List<Customer> matches = repository.searchNameLiteral(pattern);
~~~

For example, if keyword is 50%OFF, the escaped pattern is %50!%OFF%. The outer two % characters still mean substring search; the !% in the middle means a literal percent character.

If you use a different escape character, keep it consistent between the escaping code and the ESCAPE clause. Test cases containing the escape character itself, %, _, empty strings, and Unicode characters.

## 11. Do not concatenate input directly into JPQL or SQL

Do not build queries by concatenating user strings:

~~~java
// Unsafe and hard to control syntax:
String jpql =
    "select c from Customer c where c.name like '%"
    + keyword + "%'";
~~~

The right way is parameter binding:

~~~java
@Query("""
    select c
    from Customer c
    where c.name like :pattern
    """)
List<Customer> searchByPattern(
    @Param("pattern") String pattern
);
~~~

Parameter binding prevents input from becoming part of JPQL/SQL syntax. With LIKE, you still must escape wildcards if you want literal matching as shown in the previous section.

Do not use user-supplied property names, column names, or sort expressions as bind parameters; those belong to query structure. Whitelist allowed fields and expressions instead.

## 12. Useful JPQL string functions

Standard JPQL provides several common string functions:

| Function | Purpose | Example |
|---|---|---|
| LOWER(x) | Convert to lowercase | lower(c.name) |
| UPPER(x) | Convert to uppercase | upper(c.email) |
| TRIM(x) | Remove leading/trailing whitespace per function rules | trim(c.name) |
| CONCAT(a, b) | Concatenate strings | concat(c.firstName, c.lastName) |
| LENGTH(x) | String length | length(c.name) |
| LOCATE(pattern, x) | Find substring position | locate('An', c.name) |
| SUBSTRING(x, start, length) | Extract substring | substring(c.code, 1, 3) |

LOCATE returns the 1-based starting index, or 0 if not found. Exact syntax and overloads follow the Jakarta Persistence version and provider.

Example finding names with at least one character after trimming:

~~~jpql
select c
from Customer c
where length(trim(c.name)) > 0
~~~

String functions can return NULL if the input is NULL. Do not use LOWER, TRIM, or LENGTH as a substitute for IS NULL when checking for missing values.

## 13. NULL is not the same as an empty string or whitespace

Three states must be distinguished:

| Value | Meaning |
|---|---|
| NULL | No value |
| Empty string | Has a String value but contains zero characters |
| Whitespace-only string | Has characters, but no visible content |

In Java:

~~~java
String a = null;
String b = "";
String c = "   ";
~~~

These three values are not the same. c.isBlank() can return true, yet c is neither null nor an empty string.

In databases, NULL is handled by SQL logic. Empty strings are usually distinct values in PostgreSQL and MySQL. Oracle Database has special behavior treating zero-length character strings as NULL in many SQL contexts. Therefore, testing on H2 does not guarantee identical results to Oracle.

If business rules treat empty or whitespace-only strings as unentered, normalize the data before saving or apply appropriate conditions. Do not automatically treat NULL, empty strings, and whitespace as a single state unless the domain specifies it.

## 14. Three-valued logic when comparing with NULL

SQL and JPQL use three-valued logic:

- TRUE
- FALSE
- UNKNOWN

Standard comparisons with NULL typically evaluate to UNKNOWN:

| Expression | Result |
|---|---|
| NULL = NULL | UNKNOWN |
| NULL <> 'An' | UNKNOWN |
| NULL LIKE '%An%' | UNKNOWN |
| NULL NOT LIKE '%An%' | UNKNOWN |
| NULL IS NULL | TRUE |
| NULL IS NOT NULL | FALSE |

WHERE only keeps rows whose condition evaluates to TRUE. Rows evaluating to FALSE or UNKNOWN are excluded.

Therefore, the following conditions are incorrect for checking null:

~~~jpql
where c.name = null
~~~

~~~jpql
where c.name <> null
~~~

Write:

~~~jpql
where c.name is null
~~~

or:

~~~jpql
where c.name is not null
~~~

This is an important rule when combining string searches with potentially missing data.

## 15. LIKE and NOT LIKE when a property is NULL

Suppose Customer has a nullable name. The query:

~~~jpql
select c
from Customer c
where c.name like :pattern
~~~

will not return Customers whose name is NULL, because LIKE with NULL produces UNKNOWN.

Similarly:

~~~jpql
select c
from Customer c
where c.name not like :pattern
~~~

also will not return Customers whose name is NULL. NOT UNKNOWN is still UNKNOWN, not TRUE.

If business logic wants Customers whose name does not contain the keyword or who have no name yet, write it explicitly:

~~~jpql
select c
from Customer c
where c.name not like :pattern
   or c.name is null
~~~

If you want names containing the keyword or names not yet entered:

~~~jpql
select c
from Customer c
where c.name like :pattern
   or c.name is null
~~~

Decide clearly whether null should be included as a separate group or excluded from search results.

## 16. Spring Data derived queries and NULL parameters

For derived queries using equality, Spring Data JPA can translate a null parameter into an IS NULL condition. With the Not keyword and a null parameter, the query can be interpreted as IS NOT NULL.

Examples:

~~~java
List<Customer> findByName(String name);

List<Customer> findByNameIsNull();

List<Customer> findByNameIsNotNull();

List<Customer> findByNameNot(String name);
~~~

Calling findByName(null) on a derived equality query can find rows where name IS NULL. Calling findByNameNot(null) behaves correspondingly as name IS NOT NULL.

Even so, using explicit IsNull and IsNotNull method names is usually easier to read when null is an important business requirement. Do not infer that this behaves the same as a @Query with c.name = :name; in hand-written JPQL, a null parameter with = still produces UNKNOWN.

The keywords Containing, StartingWith, EndingWith, and IgnoreCase describe how to construct string predicates; they do not turn NULL into an empty string or skip the filter.

## 17. Case-insensitive search and handling NULL

If name can be NULL, the query:

~~~jpql
where lower(c.name) = lower(:name)
~~~

does not match rows where name is NULL. Applying LOWER to NULL yields NULL, and the comparison still yields UNKNOWN.

If you need to find Customers whose name equals the passed value while supporting NULL lookup, you can use two explicit branches:

~~~jpql
where (:name is null and c.name is null)
   or (:name is not null and lower(c.name) = lower(:name))
~~~

Meaning:

- When the name parameter is NULL, retrieve only entities where c.name is NULL.
- When the parameter has a value, perform a case-insensitive comparison.
- The two branches clearly separate searching for NULL from searching for non-empty strings.

If you want a null parameter to mean skipping the filter, that is a different requirement and should follow the optional filter pattern in the next section.

## 18. Optional filters with NULL parameters

A search API may allow skipping the name condition when the user does not enter a keyword.

Example:

~~~java
@Query("""
    select c
    from Customer c
    where (:keyword is null
           or lower(c.name) like lower(:pattern) escape '!')
    """)
List<Customer> searchOptionalName(
    @Param("keyword") String keyword,
    @Param("pattern") String pattern
);
~~~

Service prepares the pattern:

~~~java
String pattern = keyword == null
    ? null
    : LikePattern.containsLiteral(keyword);

return repository.searchOptionalName(keyword, pattern);
~~~

When keyword is NULL, the first branch is TRUE so the name filter is skipped. When keyword has a value, the query applies a case-insensitive LIKE with escaped wildcards.

If you also need to find rows where name is NULL, do not overload the same meaning onto a null parameter that skips the filter. Create a separate method or add a parameter representing the search mode.

When there are many optional filters, OR expressions can make queries hard to optimize. Consider Spring Data Specification, Criteria API, or dynamic queries so predicates are added only when the user actually provides conditions.

## 19. Normalizing input in the service layer

A good search rule usually starts with input normalization:

~~~java
public String normalizeKeyword(String keyword) {
    if (keyword == null) {
        return null;
    }

    String normalized = keyword.strip();

    return normalized.isEmpty() ? null : normalized;
}
~~~

This snippet uses Java 11+ String.strip() to remove Unicode whitespace from both ends. If the application runs on Java 17+, this API is available.

Decisions to make:

- Should whitespace-only input be treated as no filter or as a string to search for?
- Should Unicode NFC/NFD normalization be applied?
- Should casing be converted in Java or handled by the database via LOWER/UPPER?
- Should internal spaces within the string be preserved?
- Should diacritics be distinguished?

Do not normalize arbitrarily. For example, identifier codes may need to preserve exact casing or meaningful spaces. Normalization rules must match the domain and remain consistent between storage and search.

## 20. Impact on indexes and performance

Different string conditions have different costs:

~~~jpql
where c.email = :email
~~~

Exact comparison is usually easier to optimize with a B-tree index on the email column.

~~~jpql
where lower(c.email) = lower(:email)
~~~

Applying a function to a column can prevent the database from using a regular index as expected, depending on the optimizer and database. A functional index on lower(email), an appropriate collation, or a normalized column may be needed.

~~~jpql
where c.name like 'An%'
~~~

Prefix searches can utilize an index in some databases and collations.

~~~jpql
where c.name like '%An%'
~~~

Leading wildcards usually prevent standard B-tree indexes from helping efficiently. For large-scale substring search, consider full-text search, trigram indexes, or an appropriate search engine.

Optimization guidelines:

- Inspect execution plans instead of guessing from syntax.
- Create indexes matching real query conditions.
- Consider functional indexes for LOWER/UPPER if supported by the database.
- Normalize data into a dedicated search column if needed.
- Use full-text search when business requirements involve word matching, tokens, stemming, or ranking.
- Limit page size and returned result counts.
- Avoid running substring searches on very large tables without a proper indexing strategy.

Do not sacrifice business rules just to hit an index. First define exact semantics, then optimize queries and schema.

## 21. Combined repository example

~~~java
package example.repository;

import example.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    List<Customer> findByNameStartingWithIgnoreCase(String prefix);

    List<Customer> findByNameIsNull();

    List<Customer> findByNameIsNotNull();

    @Query("""
        select c
        from Customer c
        where lower(c.name) = lower(:name)
        """)
    List<Customer> findExactNameIgnoreCase(
        @Param("name") String name
    );

    @Query("""
        select c
        from Customer c
        where c.name like :pattern escape '!'
        """)
    List<Customer> findByLiteralNamePattern(
        @Param("pattern") String pattern
    );

    @Query("""
        select c
        from Customer c
        where (:keyword is null
               or lower(c.name) like lower(:pattern) escape '!')
        """)
    List<Customer> searchOptionalName(
        @Param("keyword") String keyword,
        @Param("pattern") String pattern
    );
}
~~~

These methods illustrate three approaches:

- Derived queries for common operations with readable method names.
- JPQL @Query when control over expressions, ESCAPE, or optional filters is needed.
- Service-layer input normalization and pattern construction before calling the repository.

In real code, choose an approach consistently based on complexity. There is no need to write a @Query for a simple condition that a derived query expresses clearly.

## 22. Testing string matching and NULL

An integration test suite should prepare data such as:

| Customer | name | email |
|---|---|---|
| 1 | An | an@example.com |
| 2 | AN | AN@example.com |
| 3 | Nguyễn An | n.an@example.com |
| 4 | An%Pro | percent@example.com |
| 5 | An_Pro | underscore@example.com |
| 6 | NULL | null-name@example.com |
| 7 | Empty string | empty@example.com |
| 8 | Whitespace only | spaces@example.com |

Verify:

1. Exact match according to database collation policy.
2. IgnoreCase for names with different letter cases.
3. Containing, StartingWith, and EndingWith.
4. Wildcards % and _ in input are escaped when literal matching is needed.
5. The escape character itself is properly escaped.
6. LIKE does not return rows with NULL values.
7. NOT LIKE also does not automatically include NULL.
8. IS NULL and IS NOT NULL return the right subsets.
9. Optional filter with null keyword skips the condition as designed.
10. Searching for an empty string differs from searching for NULL on databases that distinguish the two states.
11. Accented Vietnamese data and Unicode are handled according to the expected collation.
12. Queries do not allow SQL injection and do not let input alter query structure.

Run tests on the same database as production. H2 can differ from PostgreSQL, MySQL, Oracle, or SQL Server in collation, case sensitivity, empty strings, and string functions.

## 23. Common mistakes and fixes

**1. IgnoreCase still does not give expected results**

Check whether the property type is String, inspect generated SQL, collation, and Unicode rules. IgnoreCase is not synonymous with accent-insensitive.

**2. LIKE returns too many results**

Check whether input contains % or _. Escape wildcards if you want literal matching.

**3. LIKE fails to find strings containing % or _**

Use an ESCAPE clause and escape the input before adding substring wildcards.

**4. = NULL finds no records**

Use IS NULL. Comparisons with NULL produce UNKNOWN.

**5. NOT LIKE still skips rows with NULL values**

This is three-valued logic behavior. If you need NULLs too, add OR property IS NULL.

**6. Null parameter makes an optional filter behave wrongly**

Clarify whether null means skipping the filter or searching for NULL values. The two requirements need different predicates.

**7. Empty string is treated like NULL in production**

Check the database. Oracle has different semantics from PostgreSQL and MySQL for empty character strings.

**8. LOWER makes the query slow**

Check the execution plan and indexes. Consider a functional index or a normalized column if the workload requires it.

**9. Accent-insensitive Vietnamese search does not work**

LOWER/UPPER do not strip accents. You need an accent-insensitive collation, extension, or dedicated normalization strategy.

**10. Query works on H2 but fails in production**

Compare database engines, collations, functions, and syntax. Run integration tests on the actual database.

## 24. String search design workflow

When adding a search feature, follow this order:

1. Determine exact, prefix, suffix, or substring matching.
2. Decide whether matching is case-sensitive.
3. Decide whether Vietnamese diacritics are distinguished.
4. Check column and database collation.
5. Define what NULL, empty string, and whitespace inputs mean.
6. Choose derived query, JPQL @Query, or Criteria API.
7. For LIKE, escape % and _ if literal matching is desired.
8. Use parameter binding; never concatenate input into queries.
9. Handle IS NULL/IS NOT NULL separately from LIKE or equality.
10. Distinguish a null parameter that skips a filter from a null parameter that searches for null data.
11. Check indexes and execution plans.
12. Write integration tests with mixed case, accents, wildcards, NULL, and empty strings.
13. Run tests against the target database.

## 25. Self-assessment checklist

- [ ] I can distinguish exact match, prefix, suffix, and substring.
- [ ] I understand % and _ in LIKE.
- [ ] I know how to use Containing, StartingWith, EndingWith, and Like.
- [ ] I know how to use IgnoreCase in derived queries.
- [ ] I know how to use LOWER/UPPER in JPQL.
- [ ] I can distinguish case-insensitive and accent-insensitive.
- [ ] I understand that collation governs how strings are compared.
- [ ] I know how to escape wildcards with ESCAPE.
- [ ] I always bind parameters and never concatenate input into queries.
- [ ] I know common JPQL string functions.
- [ ] I distinguish NULL, empty strings, and whitespace strings.
- [ ] I understand UNKNOWN logic when comparing with NULL.
- [ ] I use IS NULL and IS NOT NULL appropriately.
- [ ] I understand that null parameter behavior in derived queries differs from hand-written JPQL.
- [ ] I distinguish skipping a filter from searching for NULL values.
- [ ] I understand LOWER/LIKE can affect index usage.
- [ ] I have integration tests against the production database.

## 26. Review questions

**1. How does LIKE differ from =?**

= compares values according to database equality rules; LIKE matches string patterns with % and _ wildcards.

**2. How does Containing differ from Like?**

Containing automatically adds wildcards on both ends for substring matching. Like takes a pattern supplied by the caller.

**3. Does IgnoreCase strip Vietnamese accents?**

No. IgnoreCase only handles case differences through the provider/database mechanism. Accent removal requires collation or a dedicated solution.

**4. Why must % and _ in input be escaped?**

Because those two characters are LIKE wildcards. Without escaping, they can broaden results unexpectedly when the user intends literal matching.

**5. Why does name = NULL not find rows with name NULL?**

Comparing against NULL yields UNKNOWN. Use IS NULL.

**6. Does NOT LIKE include NULL rows?**

No. NOT UNKNOWN is still UNKNOWN. To include NULL, add OR name IS NULL.

**7. Is a null parameter in a derived query the same as a null parameter in @Query?**

Not completely. Spring Data can interpret derived equality with null as IS NULL; hand-written JPQL with name = :name still follows SQL logic and will not match NULL. Write explicit predicates.

**8. Why must optional filters and NULL lookup be separated?**

Because null can mean either do not apply a condition or find rows with no value. These two meanings produce different queries and must be expressed separately.

**9. Why can LOWER(name) slow down a query?**

Applying a function to a column can prevent standard indexes from being used as expected. A functional index or normalized column may help, depending on the database.

**10. When should full-text search be used?**

When requirements go beyond simple substring matching, such as token matching, related words, ranking, stemming, or large datasets.

Good string search design starts with clear semantics: matching type, casing rules, accents, wildcards, and how NULL is interpreted. When those rules are expressed explicitly in the repository and tested against the target database, search results become more predictable and maintainable.

## References

- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Repository Query Keywords](https://docs.spring.io/spring-data/jpa/reference/repositories/query-keywords-reference.html)
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/)