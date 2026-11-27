# String Searching with Like, Containing, StartingWith, and EndingWith

## 1. String queries in Spring Data JPA

Applications often need to search data by part of a string: finding customers by part of their name, finding products by a code prefix, or filtering emails by domain. Spring Data JPA supports LIKE operators via repository method names, while also allowing JPQL via `@Query` when finer query control is needed.

Four keywords to distinguish:

- Like: uses a LIKE pattern supplied by the caller, including wildcards if needed.
- Containing: searches for a substring, automatically adding wildcards on both ends.
- StartingWith: searches for values starting with the input string, automatically adding a trailing wildcard.
- EndingWith: searches for values ending with the input string, automatically adding a leading wildcard.

All of these keywords are translated into LIKE expressions in the query. They are not four different search algorithms; the main difference is how Spring Data constructs the pattern from the input parameter.

## 2. Understanding SQL LIKE wildcards

In SQL, LIKE typically uses two wildcard characters:

| Character | Meaning | Example |
|---|---|---|
| % | Matches zero or more arbitrary characters | 'An%' matches An, Anh, An Nguyen |
| _ | Matches exactly one arbitrary character | 'A_n' matches Ann, A-n |

Example:

```sql
select *
from customer
where name like 'An%';
```

This query finds names starting with An. Using:

```sql
select *
from customer
where name like '%An%';
```

allows the string An to appear at any position. Meanwhile:

```sql
select *
from customer
where name like '%An';
```

finds names ending with An.

Whether LIKE is case-sensitive or case-insensitive depends on collation, data type, and database configuration. Do not assume LIKE is always case-sensitive across every database engine.

## 3. Using the keywords in repository method names

Suppose we have an entity:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByNameLike(String pattern);

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);
}
```

Spring Data parses the method name, resolves the property name and corresponding operator, and builds the query. The property name in the method is the entity's Java property name, not necessarily the database column name.

### 3.1. Like: the caller supplies the pattern

Method:

```java
List<Customer> findByNameLike(String pattern);
```

The parameter is used as the LIKE pattern. The caller must provide wildcards:

```java
repository.findByNameLike("An%");
repository.findByNameLike("%An%");
repository.findByNameLike("%An");
```

These respectively mean starts with An, contains An, and ends with An.

If you pass "An" without wildcards, the LIKE query is equivalent to an exact match for the string An. Like does not automatically turn every parameter into a substring search.

Because the caller controls the pattern, distinguish between searching for literal text and allowing users to enter wildcards. Do not concatenate input directly into JPQL or SQL strings; pass it through parameter binding.

### 3.2. Containing: searching for a substring anywhere

Method:

```java
List<Customer> findByNameContaining(String fragment);
```

Spring Data automatically adds wildcards on both sides of the parameter. Semantically, the query corresponds to:

```sql
where name like '%<fragment>%'
```

Example:

```java
List<Customer> results =
    repository.findByNameContaining("ng");
```

can find Nguyen, Hoang, Dang, or other names containing the string ng, depending on data and collation.

Containing has alias variants such as Contains and IsContaining in query derivation. In new code, pick one consistent naming style across the repository.

### 3.3. StartingWith: searching by prefix

Method:

```java
List<Customer> findByNameStartingWith(String prefix);
```

Spring Data appends a wildcard to the end of the parameter. Semantically:

```sql
where name like '<prefix>%'
```

Example finding names starting with An:

```java
List<Customer> results =
    repository.findByNameStartingWith("An");
```

Results can include An, Anh, An Nguyen, and other names beginning with An. This is a good fit for prefix autocomplete, searching codes starting with a string, or filtering names by their beginning.

### 3.4. EndingWith: searching by suffix

Method:

```java
List<Customer> findByNameEndingWith(String suffix);
```

Spring Data prepends a wildcard to the start of the parameter. Semantically:

```sql
where name like '%<suffix>'
```

Example finding emails ending with a domain:

```java
List<Customer> findByEmailEndingWith("@example.com");
```

In a real example, the entity/repository would need the corresponding email property. EndingWith is also useful for codes with suffixes or convention-based identifiers, though it is generally harder to utilize a standard B-tree index than prefix searching.

## 4. Comparing the four keywords

| Method keyword | Equivalent pattern | Match position |
|---|---|---|
| Like | Pattern passed by caller | Caller decides |
| Containing | %value% | Anywhere |
| StartingWith | value% | Start of string |
| EndingWith | %value | End of string |

Example passing the same string An:

| Method | Semantic pattern | Example matches |
|---|---|---|
| findByNameLike("An") | An | An |
| findByNameLike("An%") | An% | Anh, An Nguyen |
| findByNameContaining("An") | %An% | Lan, An Nguyen |
| findByNameStartingWith("An") | An% | Anh, An Nguyen |
| findByNameEndingWith("An") | %An | Hoang An |

These patterns describe LIKE semantics. Actual SQL and parameter binding are handled by Spring Data JPA/the provider; do not manually concatenate wildcards into the method name.

## 5. Case-insensitive searching

### 5.1. Using IgnoreCase

Spring Data JPA supports IgnoreCase in derived queries:

```java
List<Customer> findByNameContainingIgnoreCase(String fragment);

List<Customer> findByNameStartingWithIgnoreCase(String prefix);

List<Customer> findByNameEndingWithIgnoreCase(String suffix);
```

With IgnoreCase, Spring Data builds a case-insensitive comparison expression, typically by applying UPPER to both the property expression and the parameter. Illustrative SQL meaning:

```sql
where upper(name) like upper(?)
```

If you call:

```java
repository.findByNameContainingIgnoreCase("AN");
```

then An, AN, an, or Nguyen An can match according to the database's case handling.

### 5.2. IgnoreCase does not mean accent-insensitive

IgnoreCase handles uppercase/lowercase differences. It does not guarantee that accented and unaccented characters are treated as equivalent. For example, whether "a" matches "á" depends on collation, data type, Unicode normalization, and database features.

If a product requires accent-insensitive Vietnamese search, design explicitly for it:
- Suitable database collation.
- Normalization/diacritic-stripping function applied on both write and search.
- A dedicated normalized search column.
- An appropriate extension or full-text search if needed.

Do not strip accents only in Java on one side without normalizing the stored data accordingly; both sides must follow the same rule.

### 5.3. Impact of UPPER/LOWER on indexes

When a query applies UPPER(name), a standard B-tree index on name may not be used as expected. Depending on the database, you may need a functional index on UPPER(name), a case-insensitive collation, or a separate normalized column.

Inspect the execution plan on a real database. IgnoreCase is convenient syntactically, but it does not automatically guarantee performance.

## 6. Wildcards in input data and escaping

### 6.1. Why can % and _ alter results?

Suppose a user wants to search for the exact string "50%". If the pattern becomes %50%%, the % inside the user's input is interpreted as a wildcard. Results may match many strings that do not actually contain a percent sign.

Similarly, the underscore _ represents any single character. Without escaping, input "A_B" can match "A1B" as well.

Distinguish between:
- Wildcards intentionally supplied by the application.
- Wildcards typed by the user as part of literal text.

### 6.2. Derived Containing/StartingWith/EndingWith perform escaping

Spring Data has a mechanism to escape special wildcard characters in parameters of derived queries using Containing, StartingWith, and EndingWith, so user-entered wildcards are treated as literal characters rather than expanding the pattern. The default escape character and configuration depend on Spring Data JPA; it can be configured via escapeCharacter on @EnableJpaRepositories.

Therefore, when using these derived keywords, do not manually add wildcards to the input. For example:

```java
repository.findByNameContaining("50%");
```

is interpreted as finding strings containing the literal 50%, rather than letting the user-entered % expand as a wildcard.

### 6.3. Like takes an explicit pattern

With Like, the caller provides the pattern, so you must explicitly decide which wildcards are allowed. If you want to search for literal user input, escape % and _ according to the escape character and include the appropriate ESCAPE clause.

JPQL example using ! as the escape character:

```java
@Query("""
    select c
    from Customer c
    where c.name like :pattern escape '!'
    """)
List<Customer> searchByPattern(
    @Param("pattern") String pattern
);
```

In this example, the caller must prepare the pattern following the ! escape convention. To find literal 50%, the pattern must represent % as !% and still include outer wildcards if searching for a substring. Database and provider escape syntax should be tested.

### 6.4. Using SpEL escape in Spring Data @Query

Spring Data JPA provides `escape()` and `escapeCharacter()` helpers for queries with framework-supplied wildcards:

```java
@Query("""
    select c
    from Customer c
    where c.name like %?#{escape([0])}%
          escape ?#{escapeCharacter()}
    """)
List<Customer> findContainingLiteral(String fragment);
```

`escape()` escapes the standard SQL LIKE wildcards % and _. `escapeCharacter()` returns the escape character configured for the repository. These helpers are useful when writing a custom `@Query` while still wanting literal substring matching.

The escape helper only handles standard SQL LIKE wildcards supported by Spring Data; it does not replace verifying database-specific wildcard rules.

## 7. Null, empty strings, and user input

### 7.1. Null does not mean skip condition

If you pass null to a LIKE condition, the SQL comparison usually evaluates to UNKNOWN and returns no rows. Do not expect:

```java
repository.findByNameContaining(null);
```

to return all customers.

If a filter is optional, only add the predicate when the user actually provides a value. You can use Specification, Querydsl, or build the query conditionally in the service.

### 7.2. Empty strings can become a broad matching pattern

With Containing, an empty string can produce a pattern equivalent to %% and match every non-null name value. With StartingWith or EndingWith, a pattern equivalent to % can also match every non-null string.

This easily triggers very broad queries if a search form submits an empty string. Normalize input:
- Trim leading/trailing whitespace if business rules allow.
- Reject or ignore empty filters according to API rules.
- Limit search string length.
- Combine with Pageable or result limits.
- Avoid running a full-table contains search without sufficiently selective conditions.

### 7.3. Whitespace and Unicode

Containing searches for substrings using database comparison rules. Whitespace, Vietnamese diacritics, Unicode normalization, and collation can all affect results.

Two visually identical strings can have different Unicode encodings. If strict multilingual search is required, standardize data normalization on both write and search, and test collation on a real database.

## 8. Using @Query when condition control is needed

Derived queries are easy to read for a few simple predicates. When conditions become more complex, `@Query` expresses JPQL explicitly:

```java
@Query("""
    select c
    from Customer c
    where c.name like concat('%', :term, '%')
    order by c.name
    """)
List<Customer> searchByName(
    @Param("term") String term
);
```

This passes the parameter safely, but if term contains % or _, those characters can still act as wildcards. If you want a literal substring, use escaping as shown earlier or derived Containing.

If you need to combine multiple optional conditions, you can use Specification:

```java
public static Specification<Customer> nameContains(String term) {
    return (root, query, cb) -> {
        if (term == null || term.isBlank()) {
            return cb.conjunction();
        }

        return cb.like(
            cb.lower(root.get("name")),
            "%" + term.toLowerCase(Locale.ROOT) + "%"
        );
    };
}
```

This is an illustrative example: it handles null/blank filters but does not yet escape % and _. If term is literal user input, escape wildcard characters and specify an escape character for the Criteria predicate. `Locale.ROOT` keeps Java lowercasing consistent regardless of the default locale, though you still need to check database collation/Unicode rules.

Do not concatenate input into JPQL or SQL strings. Use parameter binding or the Criteria API to prevent syntax errors and SQL injection.

## 9. Performance of each LIKE pattern

### 9.1. StartingWith is usually friendlier to B-tree indexes

A pattern like `value%` has a fixed prefix. Many databases can use a B-tree index for prefix queries, depending on collation, operator class, and execution plan.

```sql
select id, name
from customer
where name like 'Ng%';
```

If this is a frequent query, you can create an index on name and inspect the execution plan.

### 9.2. Containing is usually hard to serve with B-tree indexes

The pattern `%value%` has no fixed prefix. A standard B-tree index normally cannot perform an efficient contiguous range scan, leading to scanning many rows.

```sql
select id, name
from customer
where name like '%ng%';
```

In PostgreSQL, the `pg_trgm` extension and GIN/GiST indexes can accelerate certain substring/LIKE queries. Other databases have full-text, n-gram, or dedicated search solutions. Choose technology based on the database and search requirements; do not assume a B-tree index will solve contains searches.

### 9.3. EndingWith is also usually hard to serve with standard B-tree indexes

The pattern `%value` has no fixed prefix and thus typically requires scanning. If suffix queries are a critical requirement, you can store a reversed string column and index it, or use a dedicated search engine. This increases write overhead and requires keeping normalized/reversed data consistent.

### 9.4. IgnoreCase and function indexes

If a query applies UPPER(name), a regular index on name may not be used. A matching functional index can help on databases that support it:

```sql
create index idx_customer_name_upper
on customer (upper(name));
```

Syntax and effectiveness depend on the database. If using a case-insensitive collation, another strategy may apply. Always check the execution plan on production-sized data.

## 10. Pagination and limiting results

Do not return tens of thousands of contains search results into a List. Use Pageable:

```java
Page<Customer> searchByNameContainingIgnoreCase(
    String fragment,
    Pageable pageable
);
```

You can call:

```java
Pageable page = PageRequest.of(
    0,
    20,
    Sort.by("name").ascending()
);

Page<Customer> result =
    repository.searchByNameContainingIgnoreCase("an", page);
```

`Page` usually requires an additional COUNT query to compute total elements; for contains searches on large tables, COUNT can also be expensive. If you only need to load more data until exhausted, consider `Slice` to avoid querying the total row count. You can also use limits like Top/First when only a small number is needed.

Pageable limits the data returned, but it does not make an unindexed LIKE query cheap. Optimize the pattern, index, or search technology before increasing page sizes.

## 11. Complete repository example

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByNameLike(String pattern);

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    Page<Customer> searchByNameContainingIgnoreCase(
        String fragment,
        Pageable pageable
    );

    List<Customer> findTop20ByNameStartingWithIgnoreCaseOrderByNameAsc(
        String prefix
    );
}
```

Invocation examples:

```java
repository.findByNameLike("Ng%");
repository.findByNameContaining("ng");
repository.findByNameStartingWith("Ng");
repository.findByNameEndingWith("son");
repository.findByNameContainingIgnoreCase("NG");
```

Each method expresses a specific search intent. Avoid overly long method names if Specification or `@Query` would make the condition easier to read and test.

## 12. Testing LIKE behavior

A repository test should cover:
- Strings matching at the start, middle, and end.
- Non-matching strings.
- Case sensitivity and IgnoreCase.
- User-entered `%` and `_` characters.
- Null and empty inputs.
- Data with Vietnamese diacritics.
- Pagination, sorting, and result limits.

Example test:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsByDifferentStringPatterns() {
        repository.saveAll(List.of(
            new Customer("Nguyen An"),
            new Customer("Tran Binh"),
            new Customer("An Nguyen"),
            new Customer("Lan")
        ));

        assertThat(repository.findByNameStartingWith("Ng"))
            .extracting(Customer::getName)
            .containsExactly("Nguyen An");

        assertThat(repository.findByNameEndingWith("Nguyen"))
            .extracting(Customer::getName)
            .containsExactly("An Nguyen");

        assertThat(repository.findByNameContainingIgnoreCase("AN"))
            .extracting(Customer::getName)
            .contains("Nguyen An", "An Nguyen", "Tran Binh");
    }
}
```

This test assumes the test database and corresponding entity/repository are configured. Result order for queries without ORDER BY is not guaranteed; if you need to assert order, declare sorting in the query or Pageable. With IgnoreCase, results depend on test data and how the database compares strings.

To test escaping and collation close to production, run integration tests on the same database type. H2 may behave differently from production databases regarding LIKE, collation, Unicode, and indexes.

## 13. Common mistakes

| Mistake | Cause | Resolution |
|---|---|---|
| Using Like without adding wildcards | Like uses the caller-supplied pattern | Pass % in the desired positions or use Containing/StartingWith/EndingWith |
| Using Containing for prefix search | Pattern has wildcards on both ends | Use StartingWith if only a prefix match is needed |
| Input containing % or _ produces overly broad results | Characters are interpreted as wildcards | Use derived keywords with escaping or escape manually in @Query |
| Null returns empty | LIKE with NULL does not evaluate to TRUE | Only add the predicate when input is present |
| Empty string returns too many rows | Pattern becomes %% or % | Validate, trim, and ignore/reject empty input |
| IgnoreCase is slow | UPPER/LOWER makes regular indexes unsuitable | Functional index, collation, or normalized column |
| Contains is slow on large tables | %term% usually cannot use B-tree effectively | Trigram, full-text, or suitable search index |
| Accent-insensitive search fails | IgnoreCase does not mean accent-insensitive | Design dedicated collation/normalization |
| Paginated results are expensive | COUNT query and large LIKE scan | Slice, limit results, index, or search engine |

## 14. Method selection checklist

- [ ] Exact match or substring search?
- [ ] Prefix, suffix, or anywhere?
- [ ] Is the caller allowed to supply wildcards?
- [ ] Should input % and _ be treated as literals or wildcards?
- [ ] Is IgnoreCase needed?
- [ ] Is Vietnamese accent-insensitive search required?
- [ ] Are null/empty inputs handled according to API rules?
- [ ] Does the query limit results or paginate?
- [ ] Is a B-tree index suitable for the pattern?
- [ ] Has the execution plan been checked on a real database?
- [ ] Have escaping, Unicode, and collation been tested?

## 15. Conclusion

Like is for caller-controlled patterns. Containing matches substrings anywhere, StartingWith matches prefixes, and EndingWith matches suffixes; the latter three add the corresponding wildcards automatically, and Spring Data handles escaping for special wildcards in derived query arguments.

IgnoreCase enables case-insensitive comparison, but it does not automatically handle Vietnamese diacritics or guarantee performance. Patterns like `%term%` generally cannot utilize B-tree indexes effectively; prefix patterns like `term%` have a better chance of using indexes. For large queries, inspect collation, indexes, and execution plans, limit results, and consider appropriate search technologies.

Choose keywords that match business intent, handle null/empty values and wildcards explicitly, use safe parameter binding, and test against a real database.