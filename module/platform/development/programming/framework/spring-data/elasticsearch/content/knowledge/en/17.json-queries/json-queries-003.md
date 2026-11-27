# Parameters ?0, ?1 and Value Substitution Mechanics

In Spring Data Elasticsearch, the @Query annotation allows declaring Elasticsearch Query DSL as a JSON string directly on a repository method. Positional placeholders such as ?0, ?1, and ?2 inject values from method parameters into the query without manual JSON string concatenation.

Placeholders are 0-indexed according to the order of the method's bindable parameters. At execution time, Spring Data processes the declared query, substitutes the placeholders with the corresponding values, and sends the query to Elasticsearch. The JSON structure and Query DSL semantics remain the responsibility of the developer.

A key point to remember is that a placeholder only represents a data value. It does not generate search conditions on its own, replace field names or operators, or determine how Elasticsearch analyzes a field. Therefore, you must write valid JSON, put placeholders in the right positions, and understand the mapping of the queried fields.

## 1. @Query and Positional Placeholders

A repository can declare a JSON query using the @Query annotation:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
    List<Product> searchByName(String text);
}
~~~

In this example:

- The JSON string in @Query is Elasticsearch Query DSL.
- ?0 is the placeholder for the first bindable parameter of the method.
- When calling searchByName("wireless keyboard"), Spring Data places the parameter value into the placeholder position.
- Elasticsearch receives a match query on the name field.

@Query is not SQL, JPQL, or derived query syntax. Spring Data does not infer conditions from the method name when an explicit JSON query is used; the JSON content determines the query structure.

## 2. Numbering ?0, ?1, ?2

Placeholders are numbered starting from 0:

| Placeholder | Corresponding Bindable Parameter |
|---|---|
| ?0 | First bindable parameter |
| ?1 | Second bindable parameter |
| ?2 | Third bindable parameter |
| ?3 | Fourth bindable parameter |

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"bool\":{\"filter\":["
            + "{\"term\":{\"category\":\"?0\"}},"
            + "{\"term\":{\"status\":\"?1\"}}"
            + "]}}")
    List<Product> findByCategoryAndStatus(
            String category,
            String status
    );
}
~~~

When called:

~~~java
repository.findByCategoryAndStatus("books", "published");
~~~

?0 receives books; ?1 receives published. The two values go into two separate term conditions.

The placeholder order must match the order of the method's bindable parameters. Swapping ?0 and ?1 may still yield valid JSON, but the conditions will filter the wrong fields.

### 2.1. Special Parameters Like Pageable and Sort

Pageable and Sort are special parameters that Spring Data uses to control pagination or sorting. They are not ordinary data values to be placed inside JSON placeholders.

Example:

~~~java
@Query("{\"match\": {\"name\": {\"query\": \"?0\"}}}")
Page<Product> searchByName(String text, Pageable pageable);
~~~

In this example, ?0 corresponds to text; Pageable controls pagination. Do not write ?1 to bind Pageable as a value inside the JSON query. Applying paging and sorting must follow the repository API of the Spring Data Elasticsearch version in use.

## 3. Substituting String Values

For a string value, the placeholder is usually placed inside a JSON string:

~~~java
@Query("{\"term\": {\"status\": \"?0\"}}")
List<Product> findByStatus(String status);
~~~

The status value is bound into that position. The double quotes in the example belong to JSON syntax enclosing the string value.

Let Spring Data's binding mechanism handle parameters. Do not concatenate user input into the query yourself:

~~~java
// Do not manually build JSON strings from input data
String json = "{\"term\":{\"status\":\"" + status + "\"}}";
~~~

Manual string concatenation easily breaks JSON when a value contains double quotes, backslashes, or control characters. It also makes code harder to maintain and can introduce untrusted data into the query structure.

Placeholders separate the fixed query structure from dynamic values. Still, validate input values against business rules and verify the binding and escaping behavior of your Spring Data version.

## 4. Substituting Numeric, Boolean, and Date/Time Values

Placeholder placement must match the JSON type expected by Elasticsearch. For numbers and booleans, values are typically not enclosed in double quotes.

Price range query example:

~~~java
@Query("{\"range\":{\"price\":{\"gte\":?0,\"lt\":?1}}}")
List<Product> findByPriceRange(
        BigDecimal minimum,
        BigDecimal maximumExclusive
);
~~~

?0 and ?1 represent the lower and upper bounds respectively. The JSON after binding needs valid numeric values.

Boolean condition example:

~~~java
@Query("{\"term\":{\"available\":?0}}")
List<Product> findByAvailable(Boolean available);
~~~

Date/time query example:

~~~java
@Query("{\"range\":{\"createdAt\":{\"gte\":\"?0\",\"lt\":\"?1\"}}}")
List<Product> findCreatedBetween(String from, String to);
~~~

For time values, standardize the input format—such as ISO-8601 with offset or UTC. The createdAt field mapping must accept that format. If using Java types like Instant, verify the binding mechanism of your Spring Data version and how the query processor converts the value into a representation Elasticsearch accepts.

Do not put quotes around numeric or boolean placeholders when the query expects a JSON number or boolean. Writing "gte":"?0" causes Elasticsearch to receive a string instead of a numeric value.

## 5. Binding Collections into a terms Query

When a parameter is a collection, a placeholder can serve as the value for a terms array:

~~~java
import java.util.Collection;
import java.util.List;

@Query("{\"terms\":{\"category\":?0}}")
List<Product> findByCategories(Collection<String> categories);
~~~

The Query DSL expects an array:

~~~json
{
  "terms": {
    "category": ["books", "games", "electronics"]
  }
}
~~~

The collection value must be converted into a JSON structure accepted by the terms query. Collection binding, element types, and null-value handling should be verified against the Spring Data Elasticsearch version in use.

A terms query is a term-level query. On keyword fields, it is typically suited for matching one of several exact values. On text fields, a terms query matches indexed terms; it does not analyze each supplied string the way a match query does.

### 5.1. Empty Lists

Do not let an empty list implicitly dictate business behavior. Before calling the repository, explicitly choose one of the following rules:

- An empty list means no selection was made, returning an empty list.
- An empty list means no category filter is applied.
- An empty list is an invalid request and should return a validation error.

Do not assume a terms query with an empty array has the same meaning as omitting the query condition. Handle this in the service layer and test the chosen behavior.

## 6. Multiple Placeholders in One Query

A single query can use multiple placeholders across different branches. Example searching products by category, price range, and status:

~~~java
@Query("{\"bool\":{"
        + "\"filter\":["
        + "{\"term\":{\"category\":\"?0\"}},"
        + "{\"term\":{\"status\":\"?1\"}},"
        + "{\"range\":{\"price\":{\"gte\":?2,\"lte\":?3}}}"
        + "]"
        + "}}")
List<Product> searchProducts(
        String category,
        String status,
        BigDecimal minimumPrice,
        BigDecimal maximumPrice
);
~~~

Parameter mapping:

| Placeholder | Method Parameter | Field or Query Position |
|---|---|---|
| ?0 | category | term.category |
| ?1 | status | term.status |
| ?2 | minimumPrice | range.price.gte |
| ?3 | maximumPrice | range.price.lte |

The JSON expression after binding represents:

~~~json
{
  "bool": {
    "filter": [
      {"term": {"category": "books"}},
      {"term": {"status": "published"}},
      {"range": {"price": {"gte": 100, "lte": 500}}}
    ]
  }
}
~~~

All conditions inside filter must match together. Using filter is appropriate for filtering conditions that do not require relevance scoring.

## 7. Placeholders Bind Values Only, Not Query Structure

A ?0 placeholder is not a variable that can arbitrarily replace any part of JSON DSL. Treat it strictly as a slot for data values.

The following cases should not be designed around placeholders:

- Replacing field names dynamically, e.g., ?0 representing category or status.
- Replacing operator names, such as term, match, or range.
- Replacing an entire arbitrary JSON branch.
- Replacing index or alias names inside a query structure.
- Replacing aggregation names or sort fields.

For example, do not expect the following query to behave as a dynamic query builder:

~~~java
// Do not treat placeholders as field names
@Query("{\"term\":{\"?0\":\"?1\"}}")
List<Product> searchDynamicField(String fieldName, String value);
~~~

If the queried field varies with input, build the query in Java using CriteriaQuery or NativeQuery and pick fields only from an allowlist. Controlling the field list prevents users from dictating query structure.

Similarly, if query structure changes based on multiple choices, construct the query object in the service instead of cramming all logic into a single @Query string.

## 8. Placeholders in Nested Bool Queries

Placeholders can appear deep inside the JSON structure as long as that position is a valid Query DSL value.

Example: status must be published and name must match a user-entered keyword:

~~~java
@Query("{\"bool\":{\"filter\":["
        + "{\"term\":{\"status\":\"?0\"}}"
        + "],\"must\":["
        + "{\"match\":{\"name\":{\"query\":\"?1\"}}}"
        + "]}}")
List<Product> searchPublishedProducts(
        String status,
        String nameText
);
~~~

?0 is used in a term-level filter; ?1 is used in a match query. Two placeholders can appear in different branches of the same JSON query.

When a query has multiple nesting levels, format the JSON legibly before turning it into a Java string. You can split it across concatenated string parts or use a text block if the project runs on a Java version that supports text blocks:

~~~java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } }
        ],
        "must": [
          { "match": { "name": { "query": "?1" } } }
        ]
      }
    }
    """)
List<Product> searchPublishedProducts(String status, String nameText);
~~~

A text block is purely a way of writing a Java string literal. It does not change placeholder rules or Elasticsearch Query DSL semantics.

## 9. Using @Query for match, term, and range

### 9.1. Match Query

~~~java
@Query("{\"match\":{\"description\":{\"query\":\"?0\"}}}")
List<Product> searchDescription(String text);
~~~

match analyzes the search string with the field's analyzer. It is suitable for text content.

### 9.2. Term Query

~~~java
@Query("{\"term\":{\"status\":\"?0\"}}")
List<Product> findByExactStatus(String status);
~~~

term matches indexed terms. For statuses or identifiers, keyword fields are usually the right choice. Do not use term on a text field expecting a verbatim phrase comparison.

### 9.3. Range Query

~~~java
@Query("{\"range\":{\"price\":{\"gte\":?0,\"lt\":?1}}}")
List<Product> findByPriceRange(
        BigDecimal minimum,
        BigDecimal maximumExclusive
);
~~~

Range queries use bounds such as gt, gte, lt, and lte. Parameter data types must match the field mapping.

## 10. Binding and Data Type Conversion

Java values must be converted into representations compatible with JSON and the Elasticsearch mapping. Common cases:

| Java Parameter Type | Common Query Position | What to Verify |
|---|---|---|
| String | String value in term or match | Quotes, escaping, and keyword/text mapping |
| Integer, Long, BigDecimal | Numeric value in range or term | Do not turn numbers into strings; matching numeric mapping |
| Boolean | Boolean value | Use JSON true/false, not strings |
| Collection<String> | Array in terms | Valid elements and empty lists |
| Instant, LocalDate, Date | Time value | Format, offset, and converter handling in your version |
| Enum | String value or converted code | Representation stored in the document must match consistently |

For custom domain types such as EmailAddress or Money, verify whether registered custom conversions are applied to query parameters. Do not assume converters used when writing entities are automatically applied identically across every binding path in @Query.

If query inputs require a specific format, you can normalize them in the service before calling the repository. This makes the input contract explicit and reduces reliance on implicit handling.

## 11. Nulls, Optional Values, and Dynamic Conditions

A placeholder does not automatically remove a JSON condition when the parameter is null. A query containing a field with a null value may not behave as intended or may be rejected by Elasticsearch depending on the query type.

For example, if status is optional, do not pass null into it by default:

~~~java
@Query("{\"term\":{\"status\":\"?0\"}}")
List<Product> findByStatus(String status);
~~~

Instead, the service should decide:

- When status has a value, use a query with the status filter.
- When status has no value, omit the status filter.

For dynamic queries, CriteriaQuery or NativeQuery is usually more appropriate because conditions can be added selectively:

~~~java
public SearchHits<Product> searchProducts(String status, String name) {
    Criteria criteria = new Criteria();

    if (status != null && !status.isBlank()) {
        criteria.and("status").is(status);
    }

    if (name != null && !name.isBlank()) {
        criteria.and("name").matches(name);
    }

    return operations.search(
            new CriteriaQuery(criteria),
            Product.class
    );
}
~~~

This snippet illustrates the idea of building a query from optional conditions; verify the Criteria API matching your project version and handle the zero-condition case per business requirements.

## 12. Pagination and Sorting with Placeholder Queries

Repository methods using @Query can be combined with Pageable when supported by the return type and version API:

~~~java
@Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
Page<Product> searchByName(String text, Pageable pageable);
~~~

?0 binds the search string; Pageable controls the page, page size, and optionally sorting. Do not put Pageable inside JSON as a placeholder value.

When using dynamic sorting, ensure the sorted field has a suitable mapping. For example, sorting by name typically requires a keyword sub-field rather than an analyzed text field. If the sort field comes from user input, validate it against an allowlist of permitted fields in Java.

## 13. Comparing @Query with CriteriaQuery and NativeQuery

| Approach | When Suitable | Advantages | Considerations |
|---|---|---|---|
| @Query with ?0, ?1 | Fixed JSON DSL with only a few substituted values | Concise; query visible right on the repository | JSON strings are harder to refactor; unsuitable for heavily changing structures |
| CriteriaQuery | Dynamic filters, field conditions, and common logical groups | Built in Java; easy to add or omit conditions | Requires understanding how Criteria translates to DSL |
| NativeQuery | Complex queries requiring control over Elasticsearch DSL | Supports bool, nested, scoring, and client features | Tied to the version's Elasticsearch Java Client API |
| Derived query method | Common, simple conditions | Method name expresses intent | Less flexible for specialized DSL or deeply nested queries |

Do not reach for @Query just because a query takes many parameters. If conditions vary with input, constructing the query in a service can be clearer than a long JSON string packed with placeholders.

## 14. Common Mistakes When Using ?0, ?1

### 14.1. Accidentally Numbering from 1

Placeholders start at ?0, not ?1. If a method has two bindable parameters, the first is ?0 and the second is ?1.

### 14.2. Reversing Parameter Order

The JSON remains valid, but values end up in the wrong fields. Maintain a clear mapping between placeholders and method arguments whenever a query has several parameters.

### 14.3. Misplacing Quotes

Strings typically belong inside JSON string positions. Numbers and booleans must sit in their corresponding JSON value positions without turning into strings. Inspect the bound query if Elasticsearch reports a parse or mapping error.

### 14.4. Using Placeholders for Field Names or Operators

Placeholders are for values. For dynamic fields or dynamic query structures, construct the query with a Java API and pick field names only from an allowlist.

### 14.5. Querying text Fields with term

@Query specifies the DSL explicitly. Using term on a text field may fail to match because the analyzer splits the text into tokens. Use match for full-text search or a keyword sub-field for exact matching.

### 14.6. Passing Null or Empty Collections

Null does not automatically drop a condition from JSON. Empty collections also require explicit business rules. Handle both in the service before invoking the repository.

### 14.7. Assuming All Java Types Bind Identically

Date/time types, enums, and value objects may require conversion. Check the exact binding path for your version and write tests for important data types.

## 15. Inspecting Queries After Substitution

When a query returns incorrect results or parse errors, check in order:

1. Is the static JSON in @Query valid?
2. Does every placeholder have the right index and position?
3. Do Java parameters have types matching the expected JSON values?
4. Are strings, numbers, booleans, and dates represented properly?
5. Do field names in the query match the mapping, including sub-fields?
6. Are the field mappings compatible with query types such as term, match, or range?
7. Are null parameters, empty collections, and large collections handled?
8. Does the actual query sent to Elasticsearch match what was intended?

In test environments, you can enable request logging appropriate for the Elasticsearch Java Client or inspect requests sent to the cluster. Logging configuration depends on the client version. Never log sensitive data if queries contain personal information, tokens, or private content.

A test suite should include:

- Normal strings.
- Strings with double quotes, backslashes, or Unicode characters.
- Numeric values at lower and upper bounds.
- Boolean true and false.
- Single-element, multi-element, and empty collections.
- Null values if allowed by the API.
- Time values with offsets and boundary timestamps.

## 16. Complete Example: Product Search Repository

Condensed entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
    List<Product> searchByName(String text);

    @Query("{\"terms\":{\"category\":?0}}")
    List<Product> findByCategories(Collection<String> categories);

    @Query("{\"bool\":{\"filter\":["
            + "{\"term\":{\"status\":\"?0\"}},"
            + "{\"range\":{\"price\":{\"gte\":?1,\"lt\":?2}}}"
            + "]}}")
    List<Product> findPublishedInPriceRange(
            String status,
            BigDecimal minimum,
            BigDecimal maximumExclusive
    );
}
~~~

Invocation:

~~~java
List<Product> matchingName =
        repository.searchByName("mechanical keyboard");

List<Product> inCategories =
        repository.findByCategories(List.of("books", "games"));

List<Product> priceRange =
        repository.findPublishedInPriceRange(
                "published",
                new BigDecimal("100"),
                new BigDecimal("500")
        );
~~~

Each method has a fixed query structure and substitutes only data values. searchByName uses match on a text field; findByCategories uses terms on a keyword field; findPublishedInPriceRange combines a term filter and a range filter.

## 17. Version Compatibility Notes

Spring Data Elasticsearch has evolved across Spring Data release trains and Elasticsearch Java Client versions. Placeholder handling, parameter types, Pageable support, and query annotations should be verified against your actual version.

When applying this in practice:

- Verify the package and @Query annotation of the exact dependency.
- Confirm positional placeholders start at 0 and map to the right bindable parameters.
- Check whether parameter types are converted as expected.
- Test queries with special values and collections.
- Verify that fields in the JSON exist and have suitable mappings.
- Observe actual queries in integration tests if results are unclear.

Do not copy query annotations from a different Spring Data version without checking the method signatures and binding behavior. If the API does not support a desired parameter type or structure, switch to CriteriaQuery or NativeQuery.

## 18. Conclusion

?0, ?1, and ?2 are positional placeholders used to pass values from repository method parameters into JSON queries declared with @Query. Indexing starts at 0 and follows the order of bindable parameters; special parameters like Pageable control pagination rather than becoming query values.

Place placeholders in the correct JSON positions: strings inside string values, numbers in numeric positions, booleans in boolean positions, and collections in array positions required by the DSL. Placeholders bind values rather than replacing field names, operators, or dynamic query structures.

Let Spring Data handle binding, verify field mappings, handle nulls and empty collections explicitly, and check actual queries in tests. For fixed queries with a few dynamic values, @Query is concise and readable; for structures that change with input or involve deep logic, CriteriaQuery and NativeQuery are usually a better fit.
