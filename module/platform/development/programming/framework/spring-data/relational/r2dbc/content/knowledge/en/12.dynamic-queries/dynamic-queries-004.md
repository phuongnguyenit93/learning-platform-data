# Null Conditions, Empty Strings, and Pattern Matching

When building dynamic queries with Spring Data R2DBC, you must clearly distinguish three cases that are often conflated: **SQL NULL values**, **empty strings**, and **whitespace-only strings**. They have different meanings in SQL and can produce different results when filtering data.

Spring Data R2DBC provides Query and Criteria to express conditions using entity metadata. You can use isNull() and isNotNull() for NULL values, is("") for empty strings, and like(pattern) for pattern matching. When conditions depend on input data, the application can append individual Criteria to the query instead of maintaining many separate SQL statements.

## 1. Distinguishing NULL, Empty Strings, and Blank Strings

Suppose the customer table has a VARCHAR column email. A row may contain the following states:

| Column value | Meaning | Example |
|---|---|---|
| NULL | No value or not yet provided | email unknown |
| Empty string | Has a string value of length 0 | '' |
| Blank string | Contains one or more whitespace characters | '   ' |
| Regular string | Has content | 'an@example.com' |

In Java, the corresponding cases might be:

~~~java
String missing = null;
String empty = "";
String blank = "   ";
String value = "an@example.com";
~~~

They are not equivalent:

- null represents the absence of a value.
- "" is a String object of length 0.
- "   " has length greater than 0 but contains no non-whitespace characters according to Java's definition of blank.
- A regular string contains data to search or compare.

Do not automatically convert all cases into null or empty strings if business rules need to distinguish them. Agree on data normalization rules at both the application and schema layers.

### 1.1. SQL NULL Has Three-Valued Logic

In SQL, comparing against NULL does not return TRUE or FALSE like normal comparisons. It returns UNKNOWN.

For example:

~~~sql
email = NULL
email <> NULL
NOT (email = 'an@example.com')
~~~

These expressions do not check for NULL as intended. With a NULL value, standard comparisons yield UNKNOWN; the WHERE clause only retains rows where the expression evaluates to TRUE.

To check for NULL, use:

~~~sql
email IS NULL
email IS NOT NULL
~~~

Example:

~~~sql
SELECT id, email
FROM customer
WHERE email IS NULL;
~~~

The query returns rows that do not yet have an email. To retrieve rows that already have an email value, use IS NOT NULL.

### 1.2. Empty Strings Are Compared as a Value

On database engines that distinguish empty strings from NULL, the condition:

~~~sql
email = ''
~~~

finds rows with an empty string. It does not find rows with NULL.

This can matter when data comes from multiple sources: a form may submit an empty string, an API may send null, and an import job may write whitespace.

A note on portability: Oracle treats zero-length character strings as NULL for ordinary character types. Therefore, queries distinguishing NULL and empty strings do not behave identically across all database engines. Verify your target database's behavior when designing schemas and search rules.

### 1.3. Whitespace-Only Strings

The string "   " is not the same as an empty string in Java and usually not the same as NULL in the database.

You can check for blank strings in Java:

~~~java
if (value == null) {
    // No value.
} else if (value.isEmpty()) {
    // String of length 0.
} else if (value.isBlank()) {
    // Only whitespace characters as defined by Java.
}
~~~

To find rows with empty or whitespace-only strings in SQL, you can use a TRIM expression depending on your database:

~~~sql
WHERE email IS NOT NULL
  AND TRIM(email) = ''
~~~

TRIM typically strips whitespace from both ends according to database rules. Whitespace definitions, Unicode characters, and collations may vary; do not assume TRIM handles all whitespace characters identically to Java's String.isBlank().

## 2. Using Criteria to Check for NULL

In Spring Data Relational, Criteria describes query conditions. With R2dbcEntityTemplate, you can use isNull() and isNotNull() to create the corresponding conditions.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    String email
) {}
~~~

### 2.1. Finding Rows with NULL Values

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
    Criteria.where("email").isNull()
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

This condition corresponds to checking email IS NULL. Prefer isNull() over passing null to is(null), because the explicit form communicates intent and avoids confusion with ordinary equality checks.

### 2.2. Finding Rows Without NULL

~~~java
Query query = Query.query(
    Criteria.where("email").isNotNull()
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

The isNotNull() condition fetches rows that have an email value. That value may still be an empty or blank string if the data permits; isNotNull() does not guarantee the string has meaningful content.

### 2.3. Finding Empty Strings

~~~java
Query query = Query.query(
    Criteria.where("email").is("")
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

This is an equality comparison against an empty string, not a NULL check. On databases that treat empty strings as NULL, results follow that specific engine's behavior.

### 2.4. Combining NULL and Empty Strings

If business logic treats both NULL and empty strings as "email not provided", both conditions can be expressed with OR:

~~~java
Criteria missingEmail =
    Criteria.where("email").isNull()
        .or("email").is("");

Query query = Query.query(missingEmail);
~~~

Semantically equivalent condition:

~~~sql
WHERE email IS NULL OR email = ''
~~~

Combine these two states only when business logic genuinely treats them as identical. If the system needs to distinguish a user leaving a field blank from a data source omitting the field, keep the two states separate.

## 3. Optional Conditions in Dynamic Queries

A search filter often has multiple optional parameters. For instance, a customer search screen may accept name, email, and active status. A user leaving a field blank usually means skipping that condition.

Do not generate an equality-with-null comparison for every parameter. If a parameter is not supplied, omit the corresponding condition. If the user wants rows with a NULL column, add an explicit isNull() condition.

Example:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<Customer> searchCustomers(
        Long tenantId,
        String name,
        String email) {

    Criteria criteria =
        Criteria.where("tenantId").is(tenantId);

    if (name != null && !name.isBlank()) {
        criteria = criteria.and("fullName")
            .like("%" + name.trim() + "%");
    }

    if (email != null && !email.isBlank()) {
        criteria = criteria.and("email")
            .is(email.trim());
    }

    Query query = Query.query(criteria);

    return template.select(Customer.class)
        .matching(query)
        .all();
}
~~~

In this example, tenantId is a mandatory condition. Name and email conditions are added only when inputs have content. This prevents an unsent parameter from inadvertently becoming a search for NULL or empty strings.

### 3.1. Distinguishing "No Filter" from "Find NULL"

A search API sometimes needs three states for a field:

1. Apply no filter.
2. Retrieve only rows with a NULL value.
3. Filter by a specific value.

If only a single String variable is used where null means both "filter omitted" and "find NULL", the application cannot tell the two intents apart.

You can represent the filter state with an enum:

~~~java
public enum EmailFilterMode {
    ANY,
    IS_NULL,
    EQUALS
}
~~~

Then build Criteria according to the mode:

~~~java
Criteria criteria =
    Criteria.where("tenantId").is(tenantId);

switch (emailFilterMode) {
    case ANY -> {
        // Do not add an email condition.
    }
    case IS_NULL ->
        criteria = criteria.and("email").isNull();
    case EQUALS -> {
        if (emailValue == null) {
            throw new IllegalArgumentException(
                "emailValue is required for EQUALS"
            );
        }
        criteria = criteria.and("email").is(emailValue);
    }
}
~~~

This representation clarifies the caller's intent. For more complex APIs, use a dedicated Filter type holding mode and value instead of multiple loose parameters.

### 3.2. Policy for Handling Empty Strings in Input

Before adding a condition, decide what an empty string means:

- Skip the filter: do not add Criteria.
- Match an exact empty string: use is("").
- Match NULL: use isNull().
- Match whitespace-only strings: use an explicit trim/blank policy or appropriate database expression.

For instance, if the application treats blank strings as absent input:

~~~java
if (name != null && !name.isBlank()) {
    criteria = criteria.and("fullName")
        .like("%" + name.trim() + "%");
}
~~~

If you need to distinguish empty strings from whitespace-only strings, do not use isBlank() to merge them. Check isEmpty() and isBlank() separately according to business rules.

## 4. Pattern Matching with LIKE

SQL LIKE uses patterns to match strings. In Spring Data R2DBC, Criteria.like(pattern) creates this condition while still using Spring's parameter binding mechanism.

Two common wildcard characters:

- % matches zero or more characters.
- _ matches exactly one character.

Examples:

| Pattern | Meaning | Matching Examples |
|---|---|---|
| 'An%' | Starts with An | An, Anh, An Nguyen |
| '%An' | Ends with An | Tran, Nguyen An |
| '%An%' | Contains An | An, Nguyen An, An Binh |
| 'A_' | A followed by one character | An, Ab |
| 'A__' | A followed by two characters | Anh, An1 |

### 4.1. Searching by Prefix

~~~java
String prefix = "Ng";

Query query = Query.query(
    Criteria.where("fullName")
        .like(prefix + "%")
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

The pattern Ng% matches names starting with Ng.

### 4.2. Searching by Suffix

~~~java
String suffix = "An";

Query query = Query.query(
    Criteria.where("fullName")
        .like("%" + suffix)
);
~~~

The pattern %An matches names ending with An.

### 4.3. Searching for Substrings Anywhere

~~~java
String keyword = "An";

Query query = Query.query(
    Criteria.where("fullName")
        .like("%" + keyword + "%")
);
~~~

The pattern %An% matches names containing An at any position.

### 4.4. Preventing Empty Strings from Creating Overly Broad Patterns

If keyword is an empty string, the pattern % + keyword + % becomes %%. This pattern can match nearly every non-NULL string value, making the query broader than intended.

Therefore, validate input before building the pattern:

~~~java
if (keyword == null || keyword.isBlank()) {
    return Flux.empty();
}
~~~

Or if business rules specify skipping the keyword condition, omit that Criteria and run the query using the remaining conditions. The two choices have different meanings: returning empty means no search when a keyword is missing; skipping the condition means searching by the other filters.

## 5. LIKE and Literal String Search

Parameter binding prevents input data from becoming part of SQL syntax. However, parameter binding does not strip wildcard meaning from % and _ inside LIKE.

For example, suppose a user enters the string 100%:

- If concatenated directly into the pattern %100%%, the user-supplied % character remains a wildcard.
- If the requirement is to match the literal % character, escape that character according to the database's LIKE syntax.

Similarly, the underscore _ is a single-character wildcard and must also be escaped when matching a literal _.

### 5.1. Escaping Wildcards in SQL

A common approach is choosing ! as the escape character:

~~~sql
SELECT id, full_name
FROM customer
WHERE full_name LIKE :pattern ESCAPE '!'
~~~

Before binding, escape the ! character itself, then % and _:

~~~java
private String escapeLikeLiteral(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
~~~

Searching for a literal string anywhere:

~~~java
String term = "100%_ready";
String pattern = "%" + escapeLikeLiteral(term) + "%";

return databaseClient.sql("""
        SELECT id, full_name
        FROM customer
        WHERE full_name LIKE :pattern ESCAPE '!'
        """)
    .bind("pattern", pattern)
    .map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            null
        )
    )
    .all();
~~~

This example uses DatabaseClient to make the ESCAPE clause explicit. Exact ESCAPE syntax and escape-character rules must be confirmed against your target database. If using Criteria.like(), verify the SQL generated by the dialect and whether escape specification is supported in your Spring Data version; do not assume every LIKE API automatically escapes wildcards.

### 5.2. Distinguishing SQL Injection from Wildcards

These two issues are distinct:

- SQL injection occurs when input data is concatenated into SQL syntax. Use bind parameters to separate data from the statement.
- LIKE wildcards are valid search pattern behavior. Even with bind parameters, % and _ can still broaden results.

Consequently, literal search requires both parameter binding and wildcard escaping. Never use string concatenation to construct SQL statements from user input.

## 6. Case-Insensitive Search

Case-comparison behavior depends on collation and the database engine. Some databases use case-insensitive collations by default; others are case-sensitive.

A fairly portable expression converts both column and pattern to the same case:

~~~sql
SELECT id, full_name
FROM customer
WHERE LOWER(full_name) LIKE LOWER(:pattern)
~~~

With DatabaseClient:

~~~java
String pattern = "%" + keyword.trim() + "%";

return databaseClient.sql("""
        SELECT id, full_name
        FROM customer
        WHERE LOWER(full_name) LIKE LOWER(:pattern)
        """)
    .bind("pattern", pattern)
    .map((row, metadata) ->
        new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class),
            null
        )
    )
    .all();
~~~

Some notes:

- LOWER/UPPER and collations may follow different rules for locales, diacritics, and Unicode.
- Applying a function to a column can prevent the database from using standard B-tree indexes; if search is critical, consider functional indexes or an appropriate collation.
- PostgreSQL has the ILIKE operator, though it is PostgreSQL-specific syntax and not portable.
- Do not assume Java-side ignore-case behavior matches database comparison rules.

## 7. Combining Multiple Condition Types in One Query

A realistic filter may combine mandatory conditions, NULL checks, exact matches, and LIKE.

Example:

~~~java
public Flux<Customer> search(
        Long tenantId,
        String keyword,
        Boolean active,
        boolean emailMissingOnly) {

    Criteria criteria =
        Criteria.where("tenantId").is(tenantId);

    if (keyword != null && !keyword.isBlank()) {
        criteria = criteria.and("fullName")
            .like("%" + keyword.trim() + "%");
    }

    if (active != null) {
        criteria = criteria.and("active").is(active);
    }

    if (emailMissingOnly) {
        criteria = criteria.and("email").isNull();
    }

    Query query = Query.query(criteria)
        .limit(50);

    return template.select(Customer.class)
        .matching(query)
        .all();
}
~~~

Here:

- tenantId is always applied.
- keyword only creates a LIKE condition when it has content.
- active is applied only when the caller supplies true or false.
- emailMissingOnly adds an IS NULL condition when enabled.

The Boolean wrapper allows distinguishing null (unfiltered) from true and false. Using a primitive boolean leaves no way to express "not provided".

When a field has multiple states, use an enum or filter object instead of overloading null with multiple meanings.

## 8. Combining OR and AND Logically

Criteria can combine multiple conditions. Pay attention to order and logical grouping because AND and OR have different precedence in SQL.

For example, finding customers whose email is NULL or an empty string, while belonging to a specific tenant:

~~~java
Criteria emailMissing =
    Criteria.where("email").isNull()
        .or("email").is("");

Criteria criteria =
    Criteria.where("tenantId").is(tenantId)
        .and(emailMissing);

Query query = Query.query(criteria);
~~~

Intended meaning:

~~~sql
WHERE tenant_id = :tenantId
  AND (email IS NULL OR email = '')
~~~

When constructing complex conditions, inspect the generated SQL to verify OR branches are enclosed in parentheses as business rules require. Do not rely solely on how code is indented.

If your version's Criteria API cannot clearly express the desired grouping, switch to DatabaseClient with explicit SQL and bind parameters.

## 9. Using Derived Queries in Repositories

For common conditions, Spring Data R2DBC can generate queries from repository method names.

Example:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByEmailIsNull();

    Flux<Customer> findByEmailIsNotNull();

    Flux<Customer> findByFullNameContaining(String fragment);

    Flux<Customer> findByFullNameStartingWith(String prefix);

    Flux<Customer> findByFullNameEndingWith(String suffix);
}
~~~

Method names express conditions:

- IsNull: finds NULL values.
- IsNotNull: finds non-NULL values.
- Containing: finds strings containing fragment.
- StartingWith: finds strings starting with prefix.
- EndingWith: finds strings ending with suffix.

Supported keywords and pattern generation rules should be verified against your Spring Data R2DBC version. When complex dynamic conditions, AND/OR groups, or custom escaping rules are needed, Query/Criteria or DatabaseClient usually communicate intent more clearly.

## 10. Normalizing Data Before Saving

One way to reduce query complexity is to establish storage normalization rules upfront.

For example, an API may adopt one of these policies:

- Email omitted: store NULL.
- Empty string received: convert to NULL or reject the request.
- Whitespace-only string received: trim and treat as empty.
- Non-empty email: trim, validate format, and store the normalized value.

Example normalization function:

~~~java
private String normalizeOptionalText(String value) {
    if (value == null) {
        return null;
    }

    String normalized = value.trim();

    return normalized.isEmpty() ? null : normalized;
}
~~~

This function collapses empty and whitespace-only strings into null. Apply it only if that matches business policy; do not use it on fields where preserving meaningful whitespace is required.

Normalizing on write reduces the number of data variations to handle at search time. However, if the database already holds legacy data in mixed forms, queries still need to cover those states or data migration must be performed.

## 11. Performance of LIKE and NULL Queries

Considerations when querying large tables:

### 11.1. LIKE with Leading Wildcards

The condition:

~~~sql
full_name LIKE 'An%'
~~~

can leverage a B-tree index in many database engines under appropriate configurations.

Meanwhile:

~~~sql
full_name LIKE '%An%'
~~~

typically cannot use a standard B-tree index due to the leading wildcard. Depending on the database, full-text search, trigram indexes, or dedicated search solutions may be needed.

### 11.2. Functions on Columns

The condition:

~~~sql
LOWER(full_name) LIKE LOWER(:pattern)
~~~

may bypass standard indexes on full_name. If large-scale case-insensitive search is needed, consider functional indexes or a suitable database collation.

### 11.3. IS NULL and IS NOT NULL

Databases may use indexes to support NULL checks depending on index type, statistics, and optimizer decisions. Measure with EXPLAIN on production-like data rather than guessing from syntax alone.

### 11.4. Avoiding Overly Broad Patterns

The pattern %% can return huge numbers of rows. Always validate inputs, cap result counts, and paginate. Never load the entire table into the application and filter in Java when the database can execute that condition.

## 12. Common Mistakes

### 12.1. Using is(null) to Check for NULL

Equality comparison with null does not express a valid SQL NULL check. Use isNull().

### 12.2. Assuming isNotNull() Excludes Empty Strings

isNotNull() can still return empty or whitespace-only strings. If both must be excluded, add the corresponding conditions and account for database differences.

### 12.3. Overloading a Null Parameter to Mean Both Skip Filter and Find NULL

These two intents differ. Use an enum or filter object to represent filter state explicitly.

### 12.4. LIKE with an Empty String Creating an Overly Broad Pattern

The pattern %% can match nearly every non-NULL value. Validate input strings before adding the condition.

### 12.5. Assuming Bind Parameters Escape Wildcards

Bind parameters ensure SQL syntax safety, but do not turn % and _ into literal characters in LIKE. If literal matching is required, escape them per database syntax.

### 12.6. Assuming Every Database Handles Empty Strings Identically

Oracle treats empty strings as NULL for ordinary character types; other engines may distinguish them. Test against your application's actual database.

### 12.7. Case-Insensitive Search Without Considering Indexes

LOWER(column) can change index usage plans. For large tables, inspect execution plans and pick an appropriate collation or index.

### 12.8. Failing to Group OR Conditions

When combining a tenant filter with (email IS NULL OR email = ''), ensure the OR group is inside parentheses. Otherwise, data from other tenants may leak.

## 13. Implementation Guidelines

- Use isNull() and isNotNull() for SQL NULL values.
- Use is("") when matching exact empty strings on databases that distinguish them from NULL.
- Decide explicitly whether blank strings are preserved, trimmed, rejected, or converted to NULL.
- Distinguish an unsent parameter from a request to find NULL values.
- Omit conditions when a filter is not provided; add isNull() only when the caller explicitly asks to filter for NULL.
- Use like(pattern) for pattern matching and understand the meaning of % and _.
- Bind parameters to prevent SQL injection; escape wildcards separately when literal matching is needed.
- Check collation, Unicode, and empty-string behavior on the target database.
- Group AND/OR conditions clearly, especially when mandatory tenant or access scopes are present.
- Cap results and check the performance of leading-wildcard patterns.
- Use derived repository queries for simple conditions; use Criteria or DatabaseClient when more complex dynamic queries are needed.

## 14. Key Takeaways

NULL represents the absence of a value and must be checked using IS NULL or IS NOT NULL. Empty strings are distinct string values on many engines; blank strings are another case requiring a normalization policy. LIKE uses % and _ as wildcards, so literal matching requires escaping those characters even when values are safely bound.

In Spring Data R2DBC, Query and Criteria help construct these conditions at the entity level. Let unsent parameters omit the corresponding condition, express NULL search requests explicitly, and choose DatabaseClient when SQL/ESCAPE clauses or database-specific logic is needed. Clear rules upfront make dynamic queries predictable and reasonably portable.
