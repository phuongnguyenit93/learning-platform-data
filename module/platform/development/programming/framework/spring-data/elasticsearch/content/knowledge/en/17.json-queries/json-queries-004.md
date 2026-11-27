# Passing Strings, Numbers, Booleans, Collections, and Special Values

In Spring Data Elasticsearch, the **@Query** annotation lets you declare Query DSL as a JSON string directly on a repository method. When a query has values that vary by input parameters, you use positional placeholders such as **?0** and **?1** so Spring Data can bind method parameter values into the query.

Passing parameters requires preserving the right JSON types. Strings must be enclosed in double quotes, numbers and booleans are unquoted JSON literals, and collections are typically passed as JSON arrays for queries such as **terms**. Beyond data types, you must pay attention to escaping special characters, null values, empty collections, dates and times, and the difference between substituting a value versus changing the Query DSL structure.

This lesson explains how to pass common parameter types in JSON queries, how to write clear repository methods, common mistakes, and when to switch to **ElasticsearchOperations** for dynamic query construction.

## 1. How Do Placeholders in @Query Work?

A repository method can declare a JSON query with placeholders:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "term": {
            "status": "?0"
          }
        }
        """)
    List<Product> findByStatusValue(String status);
}
~~~

The **?0** placeholder references the first parameter in the method's parameter list. Indexing starts at 0:

- **?0** is the first parameter.
- **?1** is the second parameter.
- **?2** is the third parameter.

Example:

~~~java
@Query("""
    {
      "range": {
        "price": {
          "gte": ?0,
          "lte": ?1
        }
      }
    }
    """)
List<Product> findInPriceRange(
    Double minPrice,
    Double maxPrice
);
~~~

Here, **?0** receives minPrice and **?1** receives maxPrice. Placeholder order must match the Java parameter order, not variable names.

You can reuse the same placeholder multiple times if the query needs the same value in multiple places. Avoid splicing a value into the query string with Java concatenation; placeholders separate the Query DSL structure from input data.

### Placeholders Only Substitute Values

Placeholders are used to pass data into value positions in JSON. Do not use them to replace field names, query names, operators, or an arbitrary JSON structural fragment.

For example, do not design a method intended to pass a field name like this:

~~~json
{
  "term": {
    "?0": "?1"
  }
}
~~~

Field names and query types are part of the request structure. If the application needs to select a field or search strategy based on runtime conditions, use code to select a controlled query structure, or construct the query using Criteria/NativeQuery. Never accept arbitrary field names from a public request and insert them into JSON.

## 2. Passing String Values

For a string value, the placeholder goes inside double quotes because Query DSL is JSON:

~~~java
@Query("""
    {
      "term": {
        "status": "?0"
      }
    }
    """)
List<Product> findByStatus(String status);
~~~

If **"ACTIVE"** is passed, the value is used for the status field. The field should have an appropriate mapping, usually **keyword** when exact matching is needed.

Mapping example:

~~~java
@Field(type = FieldType.Keyword)
private String status;
~~~

For full-text search on a text field, use **match** instead of term:

~~~java
@Query("""
    {
      "match": {
        "name": {
          "query": "?0",
          "operator": "and"
        }
      }
    }
    """)
List<Product> searchName(String phrase);
~~~

The difference lies in query semantics:

- **term** matches exact terms, usually suited for keyword fields.
- **match** analyzes the query string using the field's analyzer, suited for full-text search.

### Strings with Spaces

A string containing spaces is still an ordinary JSON string value:

~~~java
@Query("""
    {
      "match_phrase": {
        "name": "?0"
      }
    }
    """)
List<Product> findNamePhrase(String phrase);
~~~

You do not need to split the string into tokens in Java when the goal is to let the analyzer and Query DSL handle the text. Choose the right query type for the desired search behavior.

### Strings with Vietnamese Diacritics and Unicode

JSON supports Unicode. You can pass strings such as **"Bàn phím cơ"**, **"Đồ gia dụng"**, or names containing non-ASCII characters directly. Search results also depend on the field's analyzer, normalizer, and mapping.

Do not assume every analyzer handles Vietnamese diacritics the same way. If you need accent-insensitive or case-insensitive matching, configure an appropriate analyzer/normalizer and test it with real data.

## 3. Passing Numbers: Integer, Long, and Decimal

Numeric values in JSON must not be enclosed in double quotes. Range query example:

~~~java
@Query("""
    {
      "range": {
        "price": {
          "gte": ?0,
          "lt": ?1
        }
      }
    }
    """)
List<Product> findPriceRange(
    Double minPrice,
    Double maxPrice
);
~~~

If minPrice is 20.5 and maxPrice is 100.0, the values are placed in numeric positions in the JSON. The Elasticsearch field must have a compatible numeric type, such as **double**, **float**, **integer**, or **long**.

Mapping:

~~~java
@Field(type = FieldType.Double)
private Double price;

@Field(type = FieldType.Integer)
private Integer quantity;

@Field(type = FieldType.Long)
private Long viewCount;
~~~

### Do Not Pass Numbers as Strings When the Query Expects Numbers

These two JSON values have different types:

~~~json
{
  "term": {
    "quantity": 12
  }
}
~~~

~~~json
{
  "term": {
    "quantity": "12"
  }
}
~~~

The first value is a number; the second is a string. If the field is mapped as numeric, use properly typed numbers. Do not add quotes around numeric placeholders.

### Numeric Precision and Bounds

Use the Java type appropriate for the value range:

- **Integer** for integers within 32-bit limits.
- **Long** for larger integers.
- **Double** or **Float** for floating-point values when binary floating-point precision is acceptable.
- **BigDecimal** in the domain when representing currency with explicit decimal rules; when generating query JSON, ensure the value is serialized as a JSON number by the API in use.

Do not use binary floating-point numbers to store currency without accounting for rounding errors. For financial values, standardize the data type, scale, and mapping strategy when designing the index.

### Do Not Rely on Locale-Specific Number Formatting

JSON numbers use a dot for the decimal point. Do not insert strings like **"12,5"** into numeric positions because a comma is a JSON separator, not a decimal point. Pass Java numeric values and let the binding/serialization mechanism produce valid JSON literals.

## 4. Passing Booleans

Booleans in JSON are the literals **true** or **false**, lowercase and unquoted:

~~~java
@Query("""
    {
      "term": {
        "available": ?0
      }
    }
    """)
List<Product> findByAvailability(Boolean available);
~~~

Entity mapping:

~~~java
@Field(type = FieldType.Boolean)
private Boolean available;
~~~

Do not write a boolean placeholder as **"?0"** if the field is boolean. With quotes, the JSON value becomes a string instead of a boolean.

Example combining multiple types:

~~~java
@Query("""
    {
      "bool": {
        "filter": [
          { "term": { "status": "?0" } },
          { "term": { "available": ?1 } },
          { "range": { "price": { "gte": ?2 } } }
        ]
      }
    }
    """)
List<Product> searchAvailableProducts(
    String status,
    Boolean available,
    Double minPrice
);
~~~

In this example:

- status is a string, so its placeholder is quoted.
- available is a boolean, so its placeholder is unquoted.
- minPrice is a number, so its placeholder is unquoted.

## 5. Passing Collections and Arrays

For a list of values, queries typically use **terms**. The collection placeholder sits at a JSON array position and must not be enclosed in quotes:

~~~java
@Query("""
    {
      "terms": {
        "category": ?0
      }
    }
    """)
List<Product> findByCategories(Collection<String> categories);
~~~

The parameter can be a **List**, **Set**, **Collection**, or array supported by the Spring Data version's binding mechanism. Example:

~~~java
List<String> categories =
    List.of("accessories", "office", "computer");

List<Product> products =
    repository.findByCategories(categories);
~~~

With a terms query, Elasticsearch finds documents whose field value belongs to the supplied set. This is usually an exact match on a keyword field.

Mapping:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

### Numeric Collections

Numeric collections are also passed in an array position:

~~~java
@Query("""
    {
      "terms": {
        "rating": ?0
      }
    }
    """)
List<Product> findByRatings(Collection<Integer> ratings);
~~~

Elements must be compatible with the queried field type. Do not mix strings and numbers in the same collection unless the mapping and business logic clearly define how to handle it.

### Enum Collections

If the domain uses enums, standardize how enums are stored in Elasticsearch. For example, an enum stored by name:

~~~java
public enum ProductStatus {
    ACTIVE,
    DISCONTINUED,
    DRAFT
}
~~~

When passing an enum collection, verify that the converter and binding mechanism produce the exact JSON values stored by the mapping. If unsure, explicitly convert enums to a list of strings in the service layer:

~~~java
List<String> statusNames = statuses.stream()
    .map(Enum::name)
    .toList();
~~~

Do not assume enums are always serialized via name(), toString(), or a particular converter if the application has customized conversions.

### Empty Collections

An empty collection is a case that requires an explicit decision. A terms query with an empty list does not mean omitting the filter; normally it matches zero documents.

For instance, if an empty categories list means the user has not selected a category and wants all categories, do not call the method above with an empty list. Omit that filter from the query. If an empty list means no values are permitted, returning no results may be the intended behavior.

You can check before calling the repository:

~~~java
if (categories == null || categories.isEmpty()) {
    return repository.findAll();
}

return repository.findByCategories(categories);
~~~

This is only an example for a simple use case; in a real application, construct a query with the remaining filters rather than calling findAll when other conditions still apply.

## 6. Passing Dates, Times, and Temporal Values

Elasticsearch typically stores dates as temporal values indexed under a **date** or **date_nanos** mapping. JSON queries can use ISO 8601 strings or epoch values matching the configured date format.

Example:

~~~java
@Query("""
    {
      "range": {
        "createdAt": {
          "gte": "?0",
          "lt": "?1"
        }
      }
    }
    """)
List<Product> findCreatedBetween(
    String from,
    String to
);
~~~

Input values can be ISO 8601 strings, for example:

~~~text
2026-01-01T00:00:00Z
2026-02-01T00:00:00Z
~~~

Using a half-open interval **gte** and **lt** is convenient for consecutive date ranges: the start instant is included, and the end instant is excluded. This prevents adjacent ranges from overlapping at boundaries.

### Using Instant or LocalDate

In the domain, you may use **Instant**, **LocalDate**, or **OffsetDateTime**. However, how a parameter is converted into a value inside a query annotation string depends on the conversion mechanism and Spring Data Elasticsearch version.

When deterministic formatting is required, normalize the parameters into ISO 8601 strings before calling the repository:

~~~java
String fromValue = from.toString();
String toValue = to.toString();

return repository.findCreatedBetween(fromValue, toValue);
~~~

With **LocalDate**, determine the time zone and start/end of day before constructing a range. A calendar day in a specific time zone does not always correspond to a fixed 24-hour UTC span across all time zone transitions.

If a date field uses a custom format or requires date math such as **now-7d/d**, check the mapping and Query DSL. Date math is Elasticsearch value syntax, not a Java expression.

## 7. Null Values and Missing Fields

Null must be distinguished from omitting a condition from the query.

A JSON null value:

~~~json
{
  "term": {
    "discountCode": null
  }
}
~~~

does not mean querying all documents that lack discountCode. Elasticsearch does not index null values the same way as an ordinary term value unless the mapping uses an option like **null_value**. To find documents without a field, **must_not** combined with **exists** is typically used:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "discountCode"
          }
        }
      ]
    }
  }
}
~~~

### Do Not Use Null to Represent an Optional Filter

Suppose a search screen has an optional category. If category is null, business logic may intend to omit the category condition from the query.

Do not pass null into a placeholder expecting Spring Data to delete the whole clause automatically. Placeholders substitute values; they do not decide whether a query branch should be dropped.

For dynamic queries, add filters only when parameters have values:

~~~java
Criteria criteria = new Criteria();

if (category != null && !category.isBlank()) {
    criteria.and("category").is(category);
}

if (minPrice != null) {
    criteria.and("price").greaterThanEqual(minPrice);
}
~~~

This example uses Criteria to illustrate the concept. Adjust Criteria initialization and chaining to match your version's API. For complex Query DSL, use NativeQuery to conditionally include or omit individual clauses.

### Distinguishing Null, Missing, and Empty String

These three states are not identical:

| State | Meaning |
|---|---|
| null | The sent or stored value is null |
| Missing | The document does not contain that field in _source/index |
| Empty string | The field exists with an empty string "" |

How Elasticsearch indexes and queries these states depends on the mapping, null_value, and written data. Clearly define which state your business logic needs to find.

## 8. Strings with Special Characters and Escaping

User-supplied values can contain double quotes, backslashes, newlines, Vietnamese diacritics, or characters with special meaning in Query DSL.

Example string:

~~~text
Keyboard "Pro" \ Edition
~~~

When passing via placeholders, let Spring Data apply the binding and escaping mechanism supported by its version. Do not manually concatenate strings into JSON, and do not double-quote values yourself. If you assemble JSON by hand, quotes or backslashes in data can produce malformed JSON or alter query meaning.

Preferred usage:

~~~java
@Query("""
    {
      "term": {
        "displayName": "?0"
      }
    }
    """)
List<Product> findByDisplayName(String displayName);
~~~

Avoid string concatenation:

~~~java
String json = "{\"term\":{\"displayName\":\"" + displayName + "\"}}";
~~~

Concatenation like this easily fails when displayName contains quotes or backslashes. It also mixes query structure with input data.

### JSON Escaping and Query DSL Escaping Are Different Concerns

A string can be valid in JSON while still carrying special meaning for the underlying query.

For example, **query_string** uses its own syntax with characters such as:

~~~text
+ - = && || > < ! ( ) { } [ ] ^ " ~ * ? : \ /
~~~

JSON escaping only guarantees that the string is valid JSON. It does not neutralize query_string syntax. If user input is passed into query_string, those characters can be interpreted as search operators or syntax.

For regular search, prefer **match** or **multi_match** so the analyzer processes the text. Only use query_string when the product genuinely intends to offer a query language to users and has appropriate escaping/validation rules in place.

### Wildcards and Wildcard Characters

If business requirements call for wildcards, use an explicit query type:

~~~java
@Query("""
    {
      "wildcard": {
        "sku": {
          "value": "?0"
        }
      }
    }
    """)
List<Product> findBySkuPattern(String pattern);
~~~

A value like **KB-*** can use * with wildcard semantics. This is query syntax, not JSON escaping. Control pattern complexity because broad wildcards—especially patterns starting with *—can be resource-intensive.

Do not use wildcard queries as a substitute for full-text search. For long multi-word content, a match query is usually more appropriate.

## 9. Passing Multiple Types in One Query

A single query can combine strings, booleans, numbers, and collections. Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "filter": [
              {
                "term": {
                  "status": "?0"
                }
              },
              {
                "term": {
                  "available": ?1
                }
              },
              {
                "range": {
                  "price": {
                    "gte": ?2,
                    "lte": ?3
                  }
                }
              },
              {
                "terms": {
                  "category": ?4
                }
              }
            ]
          }
        }
        """)
    List<Product> searchProducts(
        String status,
        Boolean available,
        Double minPrice,
        Double maxPrice,
        Collection<String> categories
    );
}
~~~

How to read the parameters:

| Placeholder | Java Parameter | JSON Value |
|---|---|---|
| **?0** | String status | String, quoted |
| **?1** | Boolean available | Boolean, unquoted |
| **?2** | Double minPrice | Number, unquoted |
| **?3** | Double maxPrice | Number, unquoted |
| **?4** | Collection<String> categories | JSON array, no quotes wrapping the placeholder |

This example assumes all filters are mandatory and categories is non-empty. If a filter is optional, build the query dynamically instead of passing null and expecting the clause to disappear.

## 10. Parameters with Default Values and Optional Filters

Repository methods with @Query are usually best when the JSON structure is fixed. As the number of optional filters grows, a single annotation becomes awkward.

Example use case:

- keyword may be blank.
- category may be unselected.
- minPrice and maxPrice are independent.
- available may be true, false, or unfiltered.
- brand list may be empty.

Trying to force all of these into one static JSON query requires defining the exact semantics of every state. A query cannot automatically know that null means dropping a clause while false is a boolean value to filter on.

A clean implementation builds the query from criteria:

~~~java
public SearchHits<Product> search(ProductFilter filter) {
    Criteria criteria = new Criteria();

    if (filter.keyword() != null && !filter.keyword().isBlank()) {
        criteria.and("name").matches(filter.keyword());
    }

    if (filter.category() != null) {
        criteria.and("category").is(filter.category());
    }

    if (filter.minPrice() != null) {
        criteria.and("price").greaterThanEqual(filter.minPrice());
    }

    if (filter.maxPrice() != null) {
        criteria.and("price").lessThanEqual(filter.maxPrice());
    }

    Query query = new CriteriaQuery(criteria);

    return operations.search(query, Product.class);
}
~~~

This is a conceptual example; how multiple Criteria are combined—especially on the same property or for nested conditions—should be checked against your API version. When many bool branches or specialized queries are needed, NativeQuery generally provides a clearer structure.

### Distinguishing Boolean False from Unfiltered

For a nullable Boolean:

- **true** means filter documents where available is true.
- **false** means filter documents where available is false.
- **null** may mean no filter is applied.

Do not write if (available) because that ignores false. Check that available is non-null:

~~~java
if (available != null) {
    criteria.and("available").is(available);
}
~~~

This is a common bug in search filters with optional booleans.

## 11. Special Values: Enums, IDs, Text, and Domain Types

### Enums

Decide whether enums are stored by name, business code, or custom string. Query parameters must use the exact representation that was indexed.

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

If the mapping stores PAID, an exact-match query must pass PAID. If a converter stores a code like P, pass that code. Do not assume Java enums and indexed values are always identical.

### Document IDs

When querying on _id, use the appropriate query:

~~~java
@Query("""
    {
      "ids": {
        "values": ?0
      }
    }
    """)
List<Product> findByDocumentIds(Collection<String> ids);
~~~

The ids query accepts a list of IDs. Do not confuse _id with another business property named id inside _source.

### Analyzed Text Values

For text fields, a match query typically takes a string and the analyzer processes it:

~~~java
@Query("""
    {
      "match": {
        "description": {
          "query": "?0"
        }
      }
    }
    """)
List<Product> searchDescription(String text);
~~~

If you want to match the whole string exactly, use a keyword subfield and a term query. Understand the analyzer/normalizer before choosing the query.

### Geo and Structured Values

Some data types require dedicated JSON structures, such as geo points:

~~~json
{
  "geo_distance": {
    "distance": "10km",
    "location": {
      "lat": 10.78,
      "lon": 106.69
    }
  }
}
~~~

If you must pass a multi-field object such as coordinates, a range, or a nested structure, binding an entire object via one placeholder can depend on the serializer and version. You can pass scalar values separately or use NativeQuery to construct a strongly typed query object.

Do not turn a Java object into a JSON string with toString() and inject it into a query. toString() is not a JSON serializer.

## 12. Limitations of Placeholders

Placeholders are useful, but they have limits.

### Cannot Change Query Structure per Parameter

A placeholder cannot add or remove clauses by itself. If you need to choose among several query types, construct the structure in code.

### Cannot Safely Replace Field Names

Field names must remain structural elements controlled by the application. Use an allowlist to select valid fields if sort or search fields can vary.

### Cannot Handle Every Null and Empty Collection Case Automatically

The application must define the semantics of these values before calling the repository.

### Does Not Make query_string Semantically Safe

String binding separates values from JSON structure, but query_string has its own query syntax. Use an appropriate query or escape that syntax according to Elasticsearch rules.

### Does Not Replace Validation

Input still requires validation:

- Are numbers within allowed bounds?
- Is the min/max range valid?
- Does the collection exceed size limits?
- Is the string too long?
- Does the enum belong to the supported set of values?
- Do dates and times use the right format and time zone?
- Is a wildcard too broad?

Bounding input keeps queries predictable and protects cluster resources.

## 13. When to Use @Query vs. Operations?

Use **@Query** when:

- The Query DSL structure is fixed.
- Only a few scalar or collection values vary.
- The query is short enough to read and verify right in the repository.
- The return type is straightforward.
- Clauses do not need to be added or dropped dynamically at runtime.

Use **ElasticsearchOperations** with CriteriaQuery or NativeQuery when:

- There are many optional filters.
- The bool structure changes depending on input.
- Fields, query types, or nested paths must be chosen by application rules.
- Aggregations, highlighting, complex sorting, or metadata are needed.
- Target indices or aliases must be chosen at call time.
- Nulls, empty collections, or multiple data types need a unified policy.

Example using Operations with NativeQuery to add filters conditionally:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> {
        b.filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ));

        if (minPrice != null) {
            b.filter(f -> f.range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(minPrice)
                )
            ));
        }

        if (categories != null && !categories.isEmpty()) {
            b.filter(f -> f.terms(t -> t
                .field("category")
                .terms(v -> v.value(
                    categories.stream()
                        .map(FieldValue::of)
                        .toList()
                ))
            ));
        }

        return b;
    }))
    .build();

SearchHits<Product> hits =
    operations.search(query, Product.class);
~~~

This snippet illustrates conditional query construction using the Elasticsearch Java API Client builder. Builder method names and value types may differ across Spring Data Elasticsearch/client versions; adjust for your actual dependencies. The core idea is adding clauses only when business conditions are present.

## 14. Verifying Generated JSON Queries and Common Mistakes

When a @Query method returns incorrect results, check in order:

1. Are the placeholder indices right?
2. Does the Java parameter order match the placeholders?
3. Are string placeholders enclosed in double quotes?
4. Are numbers and booleans accidentally enclosed in quotes?
5. Are collections in JSON array positions?
6. Does the field mapping match the passed value type?
7. Does the query type fit text, keyword, numeric, or date?
8. Do nulls or empty collections match business semantics?
9. Do values contain characters requiring escaping?
10. Does the Query DSL have special syntax such as query_string or wildcard?

### Representative Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Invalid JSON query | Missing quotes or placeholder in the wrong position | Verify JSON and value types |
| Boolean does not match | Passed "true" instead of true | Use an unquoted Boolean placeholder |
| Range query errors or misses matches | Passed number as string or non-numeric field mapping | Use numbers and check the mapping |
| Terms query does not match | Empty collection, wrong element type, or unsuitable non-keyword field | Inspect data and mapping |
| Quoted string breaks query | Manual JSON string concatenation or broken escaping | Use placeholders; do not build JSON by hand |
| `*` or `?` produces overly broad results | Data treated as wildcard syntax | Use an explicit query type and control patterns |
| Query string alters meaning | Input characters interpreted as query_string syntax | Use match or escape query syntax |
| Null fails to return docs missing the field | Confusing null with missing | Use exists/must_not or drop the filter as needed |
| False filter is ignored | Code checks boolean with a truthy condition | Check whether value is non-null |
| Dates are shifted at range edges | Inconsistent time zones or formats | Standardize on ISO 8601 and define boundaries |

### Testing with Concrete Data

For each query, test with a small dataset covering:

- Normal strings and strings with spaces.
- Strings containing quotes, backslashes, and Unicode.
- Integers, decimals, and boundary values.
- Boolean true and false.
- Single-element, multi-element, and empty collections.
- Dates across two time zones or at day boundaries.
- Missing fields, nulls, and empty strings.

You can run equivalent JSON directly in Elasticsearch Dev Tools to separate Query DSL bugs from repository binding bugs. In the application, enable appropriate request logging in development environments to observe outbound queries. Never log sensitive data or full user parameters in production.

## 15. Complete Example with ProductRepository

Entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private Boolean available;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Date)
    private Instant createdAt;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "bool": {
            "filter": [
              { "term": { "status": "?0" } },
              { "term": { "available": ?1 } },
              { "range": { "price": { "gte": ?2, "lt": ?3 } } },
              { "terms": { "category": ?4 } }
            ]
          }
        }
        """)
    List<Product> findForCatalog(
        String status,
        Boolean available,
        Double minPrice,
        Double maxPrice,
        Collection<String> categories
    );

    @Query("""
        {
          "match": {
            "name": {
              "query": "?0",
              "operator": "and"
            }
          }
        }
        """)
    List<Product> searchName(String phrase);

    @Query("""
        {
          "range": {
            "createdAt": {
              "gte": "?0",
              "lt": "?1"
            }
          }
        }
        """)
    List<Product> findCreatedInPeriod(
        String fromIsoDate,
        String toIsoDate
    );
}
~~~

Service normalizes and validates parameters before calling the repository:

~~~java
public List<Product> findCatalog(
        String status,
        Boolean available,
        Double minPrice,
        Double maxPrice,
        Collection<String> categories) {

    if (minPrice != null && maxPrice != null
            && minPrice > maxPrice) {
        throw new IllegalArgumentException(
            "minPrice must not exceed maxPrice"
        );
    }

    if (categories == null || categories.isEmpty()) {
        // Choose another query branch per business policy.
        // Do not call a terms query with an empty collection by default.
        return List.of();
    }

    return repository.findForCatalog(
        status,
        available,
        minPrice,
        maxPrice,
        categories
    );
}
~~~

The method above illustrates validation, not the only possible policy. If empty categories means no category filtering, the service should invoke a different query without the terms clause. If empty means no category is allowed, returning an empty list may be appropriate.

For nullable filters, create dedicated methods/queries or switch to Operations so only needed clauses are added. Never pass null into range/term placeholders without verifying the resulting JSON query and intended semantics.

## 16. Principles to Remember

- Use **?0**, **?1** placeholders with 0-based parameter indexing.
- Enclose String placeholders in double quotes.
- Leave number and boolean placeholders unquoted.
- Place collection placeholders at JSON array positions, such as the value of **terms**.
- Use field mappings compatible with the data types and query types.
- Do not concatenate input strings into JSON using string addition.
- Do not use placeholders to substitute field names or Query DSL structure.
- Distinguish null, missing, and empty strings.
- Define clear semantics for empty collections.
- Normalize dates, times, and time zones before querying.
- Distinguish JSON escaping from query_string or wildcard syntax.
- Use @Query for fixed structures; use Operations when clauses are added or removed at runtime.
- Test generated queries with boundary data and real mappings.

Passing parameters with proper types keeps JSON queries structurally valid and prevents mixing data with Query DSL syntax. When only values vary, placeholders in @Query provide a concise, maintainable declaration. When the query structure itself changes with input, build the query using Operations for clear control over every condition and special value.
