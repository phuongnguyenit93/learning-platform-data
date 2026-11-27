# In, NotIn, and Handling Empty Parameter Collections

In Spring Data JDBC, the query derivation keywords **§In§** and **§NotIn§** let you filter a property against a set of values passed into the repository. For example, an application can find products whose status belongs to the set §ACTIVE§ or §PENDING§, or find products whose status is not in an excluded list.

The repository syntax is concise, but when a parameter is a collection, several scenarios must be handled explicitly:

- Non-empty collection: Spring Data JDBC generates an §IN§ or §NOT IN§ condition and binds the values.
- Empty collection: SQL list parameters are not guaranteed to work the same way across every database; do not pass an empty collection directly down to the repository.
- §null§ collection: completely different from an empty collection and requires its own input contract.
- Collection containing a §null§ element: can cause a §NOT IN§ condition to return unexpected results due to SQL three-valued logic.
- Queried column contains SQL §NULL§: both §IN§ and §NOT IN§ are subject to NULL comparison rules.

This lesson explains how to declare query methods, the semantics of parameter collections, how to handle empty collections in the service layer, and common SQL NULL scenarios.

## 1. In and NotIn in Derived Queries

Spring Data JDBC parses the repository method name to build query conditions. Two keywords are used when a parameter represents a set of values:

| Keyword | Method example | Logical condition |
| --- | --- | --- |
| §In§ | §findByStatusIn(Collection<String> statuses)§ | §status IN (:statuses)§ |
| §NotIn§ | §findByStatusNotIn(Collection<String> statuses)§ | §status NOT IN (:statuses)§ |

Suppose the §products§ table has statuses §ACTIVE§, §PENDING§, and §DISCONTINUED§. When passing the list §["ACTIVE", "PENDING"]§:

- §In§ returns products whose status is ACTIVE **or** PENDING.
- §NotIn§ returns products whose status is neither ACTIVE nor PENDING, subject to the SQL NULL rules explained later.

### 1.1. Corresponding SQL example

§§§sql
-- In
SELECT *
FROM products
WHERE status IN ('ACTIVE', 'PENDING');

-- NotIn
SELECT *
FROM products
WHERE status NOT IN ('ACTIVE', 'PENDING');
§§§

§In§ is equivalent to testing whether a value belongs to a given set. §NotIn§ negates that membership condition.

Do not confuse §NotIn§ with §Not§ on a single value:

§§§java
List<Product> findByStatusNot(String status);

List<Product> findByStatusNotIn(Collection<String> statuses);
§§§

The first method compares against **a single value**; the second compares against **a set of values**.

## 2. Declaring Repositories with In and NotIn

Suppose the aggregate root has a §status§ property:

§§§java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
        @Id Long id,
        String name,
        String status
) {
}
§§§

Repository:

§§§java
import java.util.Collection;
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<Product> findByStatusIn(Collection<String> statuses);

    List<Product> findByStatusNotIn(Collection<String> statuses);
}
§§§

Spring Data JDBC derives the query from the method name:

§§§text
findByStatusIn(statuses)
       |
       v
WHERE status IN (:statuses)

findByStatusNotIn(statuses)
       |
       v
WHERE status NOT IN (:statuses)
§§§

Collection parameters are expanded into a list of bind parameters matching the number of elements. For example, a two-element list can produce SQL like:

§§§sql
WHERE status IN (?, ?)
§§§

Values are still bound via JDBC; never concatenate input strings into SQL. Parameter binding both prevents SQL injection and lets the database handle values with the proper types.

### 2.1. Scope of query derivation

Spring Data JDBC query derivation has specific limits. It works for simple properties usable in the aggregate root's §WHERE§ clause without joining other relationships.

For example, §status§ is a direct property of §Product§:

§§§java
List<Product> findByStatusIn(Collection<String> statuses);
§§§

If you want to derive a query over a property of a referenced aggregate or a child entity inside a collection, do not assume Spring Data JDBC will automatically generate joins like an ORM. Consider an explicit SQL query or a custom repository for that case.

## 3. Non-Empty Parameter Sets

With a non-empty set, the semantics are relatively straightforward.

Suppose the data is:

§§§text
id | name          | status
---+---------------+--------------
1  | Keyboard      | ACTIVE
2  | Mouse         | PENDING
3  | Monitor       | DISCONTINUED
4  | Webcam        | ACTIVE
5  | USB Hub       | NULL
§§§

Calling:

§§§java
List<Product> products =
        repository.findByStatusIn(List.of("ACTIVE", "PENDING"));
§§§

returns Keyboard, Mouse, and Webcam. Rows with status DISCONTINUED or NULL are not selected.

Calling:

§§§java
List<Product> products =
        repository.findByStatusNotIn(List.of("ACTIVE", "PENDING"));
§§§

under standard SQL returns Monitor with status DISCONTINUED. Keyboard, Mouse, and Webcam are excluded because they match the list; USB Hub with status NULL is also excluded because the comparison evaluates to UNKNOWN.

The point about NULL is crucial and will be analyzed separately in Section 8.

## 4. An Empty Parameter Collection Is Not an Ordinary List

An empty collection has size 0:

§§§java
List<String> statuses = List.of();

System.out.println(statuses.isEmpty()); // true
§§§

From a business perspective, it can carry several different meanings:

- The user selected no statuses.
- The user wants results matching no statuses at all.
- The user wants to exclude no statuses.
- The filter was not supplied or not initialized.

These meanings are not identical. The repository cannot guess the API contract or user intent on its own.

### 4.1. Empty collection with In

By set logic, no element belongs to the empty set. Therefore, if the business requirement is "find products whose status is in the selected list" and the list has no elements, the logical result is **no products**.

You can express this in the service layer by returning an empty collection immediately:

§§§java
public List<Product> findByStatuses(
        Collection<String> statuses
) {
    if (statuses.isEmpty()) {
        return List.of();
    }

    return repository.findByStatusIn(statuses);
}
§§§

This avoids issuing pointless SQL and makes the filter's meaning explicit.

However, if the UI defines "no status selected means do not apply the filter," you must skip the condition and invoke an unfiltered query:

§§§java
public List<Product> searchByOptionalStatuses(
        Collection<String> statuses
) {
    if (statuses == null || statuses.isEmpty()) {
        return findAllProducts();
    }

    return repository.findByStatusIn(statuses);
}
§§§

This is a different contract. **An empty IN can mean either no matches or no filter depending on business logic**, and you must decide before calling the repository.

### 4.2. Empty collection with NotIn

By set logic, no value is excluded if the exclusion set is empty. Therefore, if the business rule is "find all products except those whose status is in the list," an empty list means **exclude nothing**. The service can skip the filter and return all products:

§§§java
public List<Product> findByStatusesNotIn(
        Collection<String> excludedStatuses
) {
    if (excludedStatuses.isEmpty()) {
        return findAllProducts();
    }

    return repository.findByStatusNotIn(excludedStatuses);
}
§§§

If your application defines an empty list as "no valid selection, return no results," then return an empty collection according to that contract. There is no single universal API meaning for every application.

### 4.3. Why not pass an empty collection straight to the repository?

Spring Data JDBC builds a query with a named parameter such as §IN (:statuses)§ or §NOT IN (:statuses)§. The Spring JDBC layer expands the collection into JDBC placeholders.

When the collection has no elements, there are no placeholders to expand. The SQL can end up looking like:

§§§sql
WHERE status IN ()
§§§

or:

§§§sql
WHERE status NOT IN ()
§§§

Empty-list syntax is not uniformly supported across database engines. Some databases accept one form, while others throw a syntax error; you should not rely on a single dialect's behavior to build application logic that may run on another database.

The Spring Framework documentation for §NamedParameterUtils§ warns that bind parameter lists should not be empty; empty or overly large lists are not guaranteed to be supported and are vendor-dependent. Therefore, **always handle empty collections before calling the query method**.

## 5. Distinguishing Null Collection, Empty Collection, and Non-Empty Collection

The following three inputs are different:

§§§java
Collection<String> a = null;
Collection<String> b = List.of();
Collection<String> c = List.of("ACTIVE", "PENDING");
§§§

| Input | Meaning in Java | Decision needed in service layer |
| --- | --- | --- |
| §null§ | No collection object to process. | Reject, interpret as omitted filter, or handle per API contract. |
| Empty collection | Collection exists but has zero elements. | For IN, usually no matches; for NOT IN, usually exclude nothing; may differ if API defines no filter. |
| Non-empty collection | Set of values to bind. | Call repository after normalizing and validating data. |

Do not write:

§§§java
if (statuses == null || statuses.isEmpty()) {
    return List.of();
}
§§§

mechanically for every query. For §NotIn§, that check can be wrong for business logic: an empty list typically means excluding no products, i.e., returning all of them.

Define the contract for each use case; do not reuse a single empty-handling helper for both §In§ and §NotIn§ if their semantics differ.

### 5.1. Search API example

Suppose an API receives a filter payload:

§§§json
{
  "statuses": []
}
§§§

There are at least two interpretations:

- **Filter mode:** an empty array means no statuses were selected, returning zero results.
- **Optional filter mode:** an empty array means the user has not filtered by status yet, returning all statuses.

Both can be valid. The backend must document the contract and handle it before the repository. Never let an accidental SQL syntax quirk dictate API behavior.

## 6. Normalizing and Validating Parameter Sets Before Querying

The service layer is the right place to:

- Check whether the collection is null.
- Handle an empty collection according to the business contract.
- Deduplicate values if duplicates carry no meaning.
- Check for null elements.
- Enforce a list size limit if the API imposes one.
- Normalize enums, status codes, or IDs before calling the repository.

Example of a helper that requires a non-null collection with no null elements and removes duplicates:

§§§java
import java.util.Collection;
import java.util.List;
import java.util.Objects;

private static List<String> normalizeStatuses(
        Collection<String> statuses
) {
    Objects.requireNonNull(statuses, "statuses must not be null");

    if (statuses.stream().anyMatch(Objects::isNull)) {
        throw new IllegalArgumentException(
                "statuses must not contain null"
        );
    }

    return statuses.stream()
            .map(String::trim)
            .filter(value -> !value.isEmpty())
            .distinct()
            .toList();
}
§§§

If blank strings are invalid, throw an exception instead of filtering them out; the decision must align with the API contract. Do not silently turn invalid input into a different set if doing so alters business results.

### 6.1. Handling In

§§§java
public List<Product> findByStatuses(
        Collection<String> requestedStatuses
) {
    List<String> statuses = normalizeStatuses(requestedStatuses);

    if (statuses.isEmpty()) {
        return List.of();
    }

    return repository.findByStatusIn(statuses);
}
§§§

This follows the contract "an empty set means no statuses were selected, so return no results."

If the API uses an empty collection to mean "do not apply this filter," execute the unfiltered query instead of returning §List.of()§.

### 6.2. Handling NotIn

Under the contract "an empty set means exclude nothing," you can write:

§§§java
public List<Product> findByExcludedStatuses(
        Collection<String> requestedExcludedStatuses
) {
    List<String> excluded =
            normalizeStatuses(requestedExcludedStatuses);

    if (excluded.isEmpty()) {
        return findAllProducts();
    }

    return repository.findByStatusNotIn(excluded);
}
§§§

The §findAllProducts()§ method is a helper that converts the result of §CrudRepository.findAll()§ into a §List§ if the repository does not extend §ListCrudRepository§:

§§§java
private List<Product> findAllProducts() {
    List<Product> result = new ArrayList<>();
    repository.findAll().forEach(result::add);
    return result;
}
§§§

If your project uses §ListCrudRepository§, you can receive a §List§ directly from §findAll()§. Use the repository interface appropriate for your project's Spring Data Commons version.

### 6.3. Limiting set size

A list of thousands of IDs can generate thousands of bind parameters. Consider:

- Limiting the number of items accepted from the API.
- Splitting into batches if semantics allow and merging results properly.
- Using a temporary/staging table and joining when sets are large.
- Using an array parameter or table-valued parameter if the database supports it and an appropriate custom mapping exists.
- Modeling the input as a relational table or suitable query model instead of passing a huge list.

Spring Framework notes that bind parameter lists should be kept to around 100 elements or fewer to avoid vendor dependency; this is cautious guidance for the named-parameter API, **not a uniform hard limit across all databases**. Databases and drivers also enforce their own bind parameter limits.

## 7. Complete Repository and Service Example

Aggregate:

§§§java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public record Product(
        @Id Long id,
        String name,
        String status
) {
}
§§§

Repository:

§§§java
import java.util.Collection;
import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<Product> findByStatusIn(Collection<String> statuses);

    List<Product> findByStatusNotIn(Collection<String> statuses);
}
§§§

Service:

§§§java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ProductRepository repository;

    public ProductSearchService(ProductRepository repository) {
        this.repository = repository;
    }

    public List<Product> findMatchingStatuses(
            Collection<String> requestedStatuses
    ) {
        List<String> statuses = normalize(requestedStatuses);

        // Contract: empty IN means no status matches.
        if (statuses.isEmpty()) {
            return List.of();
        }

        return repository.findByStatusIn(statuses);
    }

    public List<Product> findNotMatchingStatuses(
            Collection<String> requestedExcludedStatuses
    ) {
        List<String> excluded = normalize(requestedExcludedStatuses);

        // Contract: empty NOT IN means exclude nothing.
        if (excluded.isEmpty()) {
            return findAll();
        }

        return repository.findByStatusNotIn(excluded);
    }

    private List<String> normalize(Collection<String> values) {
        Objects.requireNonNull(values, "values must not be null");

        if (values.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException(
                    "Filter values must not contain null"
            );
        }

        return values.stream()
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .distinct()
                .toList();
    }

    private List<Product> findAll() {
        List<Product> products = new ArrayList<>();
        repository.findAll().forEach(products::add);
        return products;
    }
}
§§§

This service demonstrates two distinct semantics:

- §findMatchingStatuses(empty)§ returns an empty list.
- §findNotMatchingStatuses(empty)§ omits the exclusion filter and returns all products.

If the API defines empty as "filter not provided," both flows may need to call §findAll()§. Adjust the service branches to match your application's actual contract.

## 8. SQL NULL in the Filtered Column

Even when the parameter collection is non-empty, §IN§ and §NOT IN§ are still affected by SQL NULL values in the column.

SQL uses **three-valued logic**: §TRUE§, §FALSE§, and §UNKNOWN§. A §WHERE§ clause keeps a row only when the expression evaluates to §TRUE§; both §FALSE§ and §UNKNOWN§ are excluded.

Suppose §status§ can be NULL:

§§§sql
SELECT *
FROM products
WHERE status NOT IN ('ACTIVE', 'PENDING');
§§§

A row with §status IS NULL§ is not selected because comparing against NULL evaluates to UNKNOWN.

### 8.1. Logical result table

For the set §('ACTIVE', 'PENDING')§:

| Column value | §status IN (...)§ | §status NOT IN (...)§ |
| --- | --- | --- |
| §'ACTIVE'§ | TRUE | FALSE |
| §'PENDING'§ | TRUE | FALSE |
| §'DISCONTINUED'§ | FALSE | TRUE |
| §NULL§ | UNKNOWN | UNKNOWN |

If the business requirement for §NotIn§ is "not in the list or status unset," add the explicit null condition:

§§§sql
SELECT *
FROM products
WHERE status NOT IN ('ACTIVE', 'PENDING')
   OR status IS NULL;
§§§

If you only want rows whose status is non-NULL and not in the list:

§§§sql
SELECT *
FROM products
WHERE status IS NOT NULL
  AND status NOT IN ('ACTIVE', 'PENDING');
§§§

Do not assume §NotIn§ means "any value outside the list, including NULL." SQL does not interpret it that way.

### 8.2. NULL columns with In

§IN§ also does not match rows with a NULL column:

§§§sql
SELECT *
FROM products
WHERE status IN ('ACTIVE', 'PENDING');
§§§

If you also want products without a status:

§§§sql
SELECT *
FROM products
WHERE status IN ('ACTIVE', 'PENDING')
   OR status IS NULL;
§§§

If you need this query frequently, you can define a derived method with an OR condition on the same property if supported by the syntax and version, or use an explicit §@Query§.

## 9. NULL Elements Inside the Parameter Collection

A different case from a NULL column is **an input collection containing a Java null element**.

Example:

§§§java
List<String> statuses =
        Arrays.asList("ACTIVE", null);
§§§

When expanded into SQL, the condition can correspond to:

§§§sql
WHERE status NOT IN ('ACTIVE', NULL)
§§§

For §status = 'DISCONTINUED'§, the database must evaluate:

§§§text
'DISCONTINUED' <> 'ACTIVE'  -> TRUE
'DISCONTINUED' <> NULL      -> UNKNOWN

TRUE AND UNKNOWN            -> UNKNOWN
§§§

Because §WHERE§ only accepts TRUE, the DISCONTINUED row is also excluded. A single NULL value in a §NOT IN§ list can prevent ordinary non-matching rows from being returned as expected.

With §IN§, a NULL element likewise does not mean "also find rows whose column is NULL." For example, §status IN ('ACTIVE', NULL)§ still will not return rows with a NULL status; the comparison on that row evaluates to UNKNOWN.

**Recommendation:** never put null inside an §In§/§NotIn§ collection. Separate the request for NULL into a dedicated §IS NULL§ condition.

If you want to filter for status ACTIVE or NULL:

§§§sql
WHERE status = 'ACTIVE'
   OR status IS NULL
§§§

If you want statuses other than ACTIVE, while still excluding NULL:

§§§sql
WHERE status IS NOT NULL
  AND status <> 'ACTIVE'
§§§

If you want statuses other than ACTIVE and also keep NULL:

§§§sql
WHERE status <> 'ACTIVE'
   OR status IS NULL
§§§

### 9.1. Why should the service reject null elements?

Rejecting null avoids queries with unpredictable semantics for callers:

§§§java
if (statuses.stream().anyMatch(Objects::isNull)) {
    throw new IllegalArgumentException(
            "Use an explicit null predicate instead of null in the IN list"
    );
}
§§§

If the application contract intends to ignore null elements, you can filter them out before querying, but make that clear in the API. Never silently treat null as a value that matches SQL NULL.

## 10. NULL Collection Parameter vs. NULL Element

These three cases must be handled separately:

§§§java
Collection<String> statuses = null;              // Null collection
Collection<String> empty = List.of();            // Empty collection
Collection<String> containsNull =
        Arrays.asList("ACTIVE", null);            // Contains null element
§§§

| Case | Issue | Recommended handling |
| --- | --- | --- |
| Null collection | Unclear whether caller omitted the filter or passed invalid input. | Define the contract; usually validate/reject or treat as filter absent in the service. |
| Empty collection | No placeholder for an IN list. | Handle per business semantics before calling the repository. |
| Collection containing null | SQL three-valued logic can prevent NOT IN from returning expected results. | Reject, strip intentionally, or express NULL via a separate predicate. |

Do not treat §null§ and an empty collection as interchangeable ways of saying "no filter." They are two distinct input states and should have distinct API contracts.

## 11. Combining In/NotIn with Other Conditions

Query derivation lets you combine conditions using §And§ and §Or§ when properties fall within supported scope.

Example:

§§§java
List<Product> findByStatusInAndActiveTrue(
        Collection<String> statuses
);

List<Product> findByStatusNotInAndCategoryId(
        Collection<String> excludedStatuses,
        Long categoryId
);
§§§

Meaning:

§§§sql
WHERE status IN (:statuses)
  AND active = TRUE
§§§

and:

§§§sql
WHERE status NOT IN (:excludedStatuses)
  AND category_id = :categoryId
§§§

However, if the collection is empty, the service still needs to handle it before calling these methods. For example, §In(empty)§ may make the entire AND condition impossible to match; §NotIn(empty)§ may drop only the NOT IN predicate while keeping the category filter.

Do not discard the entire query just because one parameter set is empty if the remaining conditions are still meaningful. Build a clear contract for each filter.

### 11.1. Example: filtering by category and status list

§§§java
public List<Product> findProducts(
        Long categoryId,
        Collection<String> statuses
) {
    List<String> normalized = normalize(statuses);

    if (normalized.isEmpty()) {
        return List.of();
    }

    return repository.findByCategoryIdAndStatusIn(
            categoryId,
            normalized
    );
}
§§§

If the status filter is optional, you may need two methods or a custom query to omit only the status predicate when the list is empty. Do not call an §In§ method with an empty list hoping the database will interpret it as skipping the filter.

## 12. When the Parameter Collection Is Too Large

§IN§ and §NOT IN§ are convenient for small sets, but not optimal for every size.

For example, a request passing 20,000 IDs can result in:

- A very long SQL statement.
- Huge numbers of bind parameters.
- Hitting database/driver parameter limits.
- Higher SQL parse/plan overhead.
- Increased memory and data transfer time.
- Poor plan cache reuse if the placeholder count keeps changing.

Options to consider:

| Scale / Scenario | Approach to consider |
| --- | --- |
| Small set, a few values | Derived query §In§/§NotIn§ is usually suitable. |
| Medium set, clear upper bound | Validate size; verify DB/driver limits. |
| Large set, batching required | Split into multiple queries and merge results carefully per semantics. |
| Very large or reused set | Load IDs into a staging/temp table and JOIN. |
| Database supports array/table-valued parameters | Use database-specific features via custom repository/appropriate conversion. |
| Input data represents a business relationship | Model it as a relational table rather than passing a giant list. |

### 12.1. Batching is not trivial for NotIn

With §In§, splitting a set into batches lets you fetch each batch and combine results, provided pagination, sorting, or limits do not introduce duplicates or ordering errors.

With §NotIn§, you cannot simply run multiple §NOT IN§ queries per batch and combine their results:

§§§text
NOT IN (batch A)
AND NOT IN (batch B)
§§§

To exclude all elements from both batches, the conditions must be combined with AND. If you union or OR the results of separate queries, you will bring back rows that should have been excluded. Design the query and combination logic according to proper set logic.

For large exclusion sets, a staging table or reference table is usually much easier to manage than stitching together hundreds of §NOT IN§ queries.

## 13. When to Use Derived Queries vs. @Query?

Derived queries are clear for simple conditions:

§§§java
List<Product> findByStatusIn(Collection<String> statuses);

List<Product> findByStatusNotIn(Collection<String> statuses);
§§§

When you need to express more complex conditions such as:

§§§sql
WHERE status NOT IN (:excluded)
   OR status IS NULL
§§§

you can use §@Query§:

§§§java
import java.util.Collection;
import java.util.List;

import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
        SELECT id, name, status
        FROM products
        WHERE status NOT IN (:excluded)
           OR status IS NULL
        """)
List<Product> findByStatusNotInOrStatusIsNull(
        @Param("excluded") Collection<String> excluded
);
§§§

This example assumes §excluded§ has already been validated in the service as **non-empty and containing no nulls**. If the collection is empty, you still need a branch before the repository; §@Query§ does not solve the empty-list issue automatically.

When using a query string, return columns that match the aggregate mapping. With this query, §id§, §name§, and §status§ cover all properties of §Product§ in the example.

If dynamic conditions across many optional filters are needed, a custom repository or query builder may fit better than a long method name.

## 14. Common Mistakes

**“In with an empty list always returns an empty list.”** That is the desired business-layer semantics under set theory, but SQL empty-list syntax is not uniformly supported. Return an empty collection in the service rather than sending an empty list to the repository.

**“NotIn with an empty list always returns all rows.”** Do not rely on SQL §NOT IN ()§. If the business rule is to exclude nothing, skip the predicate and call the appropriate query.

**“A null collection is the same as an empty collection.”** No. Null may mean filter absent or invalid input; empty means a collection exists with zero elements.

**“Putting null in the list is how to find NULL columns.”** Incorrect. Use §IS NULL§ or §OR status IS NULL§.

**“NotIn automatically returns rows with NULL columns too.”** Incorrect. §NULL NOT IN (...)§ evaluates to UNKNOWN and is filtered out by WHERE unless an explicit IS NULL condition is added.

**“Checking for null elements can be skipped.”** Do not skip it. A single null element in §NOT IN§ can keep other rows from being selected as expected.

**“Spring Data JDBC automatically deduplicates values.”** Do not assume so. If input sets may contain duplicates that carry no meaning, normalize with §distinct()§ before calling the repository.

**“Bigger lists are always fine because it is just one SQL statement.”** Incorrect. Databases and drivers have bind parameter limits; overly large SQL statements can be slow and resource-intensive.

**“Use NotIn instead of a null check.”** Incorrect. §NOT IN§ and §IS NOT NULL§ are two different conditions.

**“Derived queries auto-join to any property.”** Incorrect in Spring Data JDBC. Query derivation is limited to properties that can be used directly in WHERE without joining.

## 15. Safe In/NotIn Processing Workflow

When receiving a collection parameter for querying, follow these steps:

1. **Define the contract:** does empty mean no matches, no filter, or exclude nothing?
2. **Check for null collection:** reject or treat as filter absent according to the contract.
3. **Check for null elements:** reject or separate into an explicit IS NULL predicate.
4. **Normalize values:** trim, convert enums, and deduplicate if permitted by business logic.
5. **Handle empty collections:** decide the outcome in the service; never call the repository with an empty list.
6. **Limit size:** avoid exceeding database or driver limits.
7. **Call the query method:** use In/NotIn for small sets and simple root properties.
8. **Account for SQL NULL in the column:** if NULLs should be included, add an explicit predicate.
9. **Measure queries:** for large sets, inspect execution plans and consider staging tables or custom SQL.

§§§mermaid
flowchart TD
    A["Receive filter Collection"] --> B{"Collection null?"}
    B -->|Yes| C["Reject or handle filter absent<br/>per API contract"]
    B -->|No| D{"Contains null element?"}
    D -->|Yes| E["Reject or separate IS NULL predicate"]
    D -->|No| F["Normalize / distinct / validate size"]
    F --> G{"Collection empty?"}
    G -->|Yes| H{"In or NotIn<br/>and what is the contract?"}
    H --> I["In: no matches or omit filter"]
    H --> J["NotIn: exclude nothing or per contract"]
    G -->|No| K["Call repository In / NotIn"]
    K --> L["Evaluate SQL NULL in column"]
    L --> M["Return results"]
§§§

## 16. Practice Exercises

Create a §products§ table with columns §id§, §name§, and §status§. Insert rows with ACTIVE, PENDING, DISCONTINUED, and one row with status NULL.

### Exercise 1: In with a non-empty set

1. Declare §findByStatusIn(Collection<String> statuses)§.
2. Pass §["ACTIVE", "PENDING"]§.
3. Confirm only statuses in the list are returned.

### Exercise 2: NotIn with a non-empty set

1. Declare §findByStatusNotIn(Collection<String> statuses)§.
2. Pass §["ACTIVE", "PENDING"]§.
3. Observe that the DISCONTINUED row is returned.
4. Observe that the row with status NULL is excluded.
5. Write a query adding §OR status IS NULL§ and compare.

### Exercise 3: Empty collection

1. Call the service method §findMatchingStatuses(List.of())§.
2. Confirm the service returns an empty list per the no-matches contract without calling the repository.
3. Call §findNotMatchingStatuses(List.of())§.
4. Confirm the service omits the predicate and returns all products per the exclude-nothing contract.
5. Try changing the empty contract to no-filter and adjust the service branch.

### Exercise 4: Null collection

1. Pass §null§ to the service.
2. Confirm the input is rejected or handled according to the chosen contract.
3. Do not let a null failure occur late during SQL generation.

### Exercise 5: Collection containing null

1. Pass §["ACTIVE", null]§ to the NotIn method.
2. Observe SQL three-valued logic.
3. Replace with validation that rejects null.
4. If business logic requires including status NULL, write a separate §OR status IS NULL§ predicate.

### Exercise 6: Large sets

1. Test ID lists of increasing size.
2. Observe placeholder counts and database/driver limits.
3. Compare an IN-list query against a staging table or database-specific solution for large sets.
4. Record the execution plan and timing for the same dataset.

## 17. Key Takeaways

- §In§ generates §property IN (:values)§; §NotIn§ generates §property NOT IN (:values)§.
- Spring Data JDBC supports both keywords in query derivation with collection parameters.
- Non-empty collections expand into JDBC bind parameters; never concatenate input strings into SQL.
- Empty collections are not guaranteed to be supported uniformly by databases. Handle them in the service layer before calling the repository.
- By set logic, §In(empty)§ usually means no results; §NotIn(empty)§ usually means exclude nothing. An API contract may choose different semantics, but it must be defined explicitly.
- Null collection, empty collection, and collection containing null are three distinct cases.
- SQL NULL in a parameter collection or in a column can cause §IN§/§NOT IN§ to evaluate to UNKNOWN; §WHERE§ does not keep UNKNOWN rows.
- Use §IS NULL§/§IS NOT NULL§ when handling NULL values; never place null in a list as a substitute for that predicate.
- Overly large lists can exceed bind parameter limits or degrade query performance; consider batching, staging tables, or database-specific mechanisms.
- Spring Data JDBC query derivation is limited to properties usable in WHERE without joins.

When using §In§ and §NotIn§, what matters is not only method name syntax but also **parameter set semantics**. Explicitly handling empty collections, null collections, null elements, and SQL NULL ensures consistent results across environments and alignment with your business contract.

## References

- [Spring Data Relational — Query Methods (JDBC)](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Framework — NamedParameterUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterUtils.html)
- [Spring Data Relational — Query Predicate Keywords](https://docs.spring.io/spring-data/relational/reference/repositories/query-keywords-reference.html)
