# Method Name Structure and Property Path Resolution

Spring Data Elasticsearch can generate queries from repository method names. Instead of writing Query DSL for every simple condition, you declare a method such as `findByStatusAndTotalGreaterThan`; Spring Data parses the name, locates the corresponding properties in the entity, and builds an appropriate query.

This mechanism is called *query derivation*. To use it correctly, you need to understand two distinct processes:

1. **Method name structure parsing:** Spring Data identifies the subject prefix, the `By` delimiter, predicates, operators, and sort order.
2. **Property path resolution:** Spring Data determines whether each name segment points to a direct property or a nested property inside another object.

Incorrect resolution or ambiguous property names can cause the application to query the wrong field, produce unexpected queries, or fail to start the repository. This lesson focuses on naming rules, how the parser resolves properties, how to handle nested paths, and how to diagnose errors in Spring Data Elasticsearch.

## 1. The query derivation mechanism

A derived query typically takes the form:

~~~text
findBy<Property><Operator><Value>
~~~

For example:

~~~java
List<Product> findByCategory(String category);
~~~

Spring Data reads the method name and recognizes:

- `find` is the subject prefix indicating a query operation.
- `By` marks the beginning of the predicate section.
- `Category` is the property to match.
- The `category` parameter supplies the value for the condition.

For a method with multiple conditions:

~~~java
List<Product> findByCategoryAndPriceLessThan(
    String category,
    Double maxPrice
);
~~~

The parser identifies two conditions joined by `And`:

- `Category` matches against the first parameter.
- `PriceLessThan` compares the price as less than the second parameter.

Spring Data uses entity metadata to locate properties and their data types. Then, Spring Data Elasticsearch translates the query representation into a request suitable for Elasticsearch.

Method names form a declarative language with strict rules. They are not arbitrary Java expressions evaluated by ad-hoc string parsing, nor are they endpoint names or raw JSON field names written directly.

## 2. Parts of a method name

A common structure can be visualized as follows:

~~~text
findDistinctTop10ByStatusAndTotalGreaterThanOrderByCreatedAtDesc
|----subject----|By|----------predicate----------|---ordering---|
~~~

A method name has three main parts:

| Part | Role |
|---|---|
| Subject | Indicates the operation type or result limit |
| `By` | Separates the subject and the predicate |
| Predicate | Specifies the properties, operators, and values to check |
| `OrderBy` | Optional part specifying the sort order |

`OrderBy` sits inside the method name after the predicate, but it can be treated as a separate part because it describes result ordering rather than filtering conditions.

### Subject: the introductory part

Common introductory keywords in Spring Data include:

- `findBy`
- `readBy`
- `getBy`
- `queryBy`
- `searchBy`
- `streamBy`

Spring Data Elasticsearch supports a specific set of methods and return types depending on the version. Therefore, treat the words above as common introductory forms in Spring Data repositories and verify the supported forms in the release train you are using.

Some methods can use the subject to limit or describe the result:

~~~java
List<Product> findTop10ByCategory(String category);

Optional<Product> findFirstBySku(String sku);

long countByCategory(String category);

boolean existsBySku(String sku);
~~~

`Top` and `First` can limit the number of results. The following number specifies the limit, such as `Top10`. `countBy` and `existsBy` express counting or existence checks if the repository version supports those methods.

Do not confuse the subject with property names. In `findDistinctTop10ByCategory`, `Distinct` and `Top10` are subject modifiers; properties start after `By`.

### Predicate: the condition part

The predicate starts immediately after `By` and contains properties along with operators:

~~~java
findByStatus(String status)
findByPriceGreaterThan(Double price)
findByCreatedAtBetween(Instant from, Instant to)
findByNameContaining(String text)
~~~

A predicate can contain multiple conditions:

~~~java
findByStatusAndCategory(String status, String category)
findByStatusOrCategory(String status, String category)
~~~

The parameter order must match the order of conditions in the method name. If you reorder properties without reordering parameters, the query may use the wrong values.

### Ordering: the sorting part

You can declare a fixed order using `OrderBy`:

~~~java
List<Product> findByCategoryOrderByPriceAsc(String category);

List<Product> findByCategoryOrderByCreatedAtDesc(
    String category
);
~~~

`Asc` specifies ascending order; `Desc` specifies descending order. When dynamic sorting per request is needed, it is usually better to accept `Pageable` or `Sort` rather than creating separate methods for each sort order.

## 3. Operators in predicates

Spring Data recognizes operator keywords placed after a property. Some commonly used forms:

| Keyword in name | Intended meaning | Example |
|---|---|---|
| No suffix, `Is`, `Equals` | Equality match | `findByStatus` |
| `Not`, `IsNot` | Not equal | `findByStatusNot` |
| `GreaterThan` | Greater than | `findByPriceGreaterThan` |
| `GreaterThanEqual` | Greater than or equal | `findByPriceGreaterThanEqual` |
| `LessThan` | Less than | `findByPriceLessThan` |
| `LessThanEqual` | Less than or equal | `findByPriceLessThanEqual` |
| `Between` | Within a range | `findByPriceBetween` |
| `In` | Within a set of values | `findByStatusIn` |
| `NotIn` | Not within a set of values | `findByStatusNotIn` |
| `Like` | Matches according to a supported pattern form | `findByNameLike` |
| `Containing` | Finds content containing a string per supported semantics | `findByNameContaining` |
| `StartingWith` | Starts with string | `findByCodeStartingWith` |
| `EndingWith` | Ends with string | `findByCodeEndingWith` |
| `True`, `False` | Boolean check | `findByActiveTrue` |
| `IsNull`, `IsNotNull` | Null value check | `findByDeletedAtIsNull` |

These are familiar keywords across the Spring Data ecosystem. Not every keyword is supported or has identical semantics in every version of Spring Data Elasticsearch. Check the reference documentation for your project's version before using a less common keyword.

In particular, words such as `Containing`, `Like`, `StartingWith`, and `EndingWith` should not be interpreted mechanically in SQL terms. Elasticsearch has its own analyzers, tokens, and Query DSL. The field type, analyzer, and generated query will affect the results.

### Example with a product entity

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    private Boolean active;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByPriceGreaterThan(Double price);

    List<Product> findByPriceBetween(
        Double minPrice,
        Double maxPrice
    );

    List<Product> findBySkuIn(Collection<String> skus);

    List<Product> findByActiveTrue();
}
~~~

Each method uses Java property names: `category`, `price`, `sku`, and `active`. Spring Data looks up each property in the entity and uses mapping metadata to determine the type of the corresponding Elasticsearch field.

## 4. Combining conditions with And and Or

A predicate can combine multiple conditions using `And` or `Or`:

~~~java
List<Product> findByCategoryAndActive(
    String category,
    Boolean active
);

List<Product> findByCategoryOrName(
    String category,
    String name
);
~~~

These can be read sequentially as:

- `findByCategoryAndActive`: category satisfies the condition and active satisfies the condition.
- `findByCategoryOrName`: category satisfies the condition or name satisfies the condition.

When mixing `And` and `Or`, pay close attention to how the parser groups conditions. Spring Data splits on OR groups; conditions joined by AND stay within the same group. For example:

~~~java
findByStatusAndCategoryOrFeaturedTrue(
    String status,
    String category
)
~~~

This can be read structurally as:

~~~text
(status = ?0 AND category = ?1) OR (featured = true)
~~~

Avoid writing long method names with many `And` and `Or` keywords if readers struggle to determine how conditions are grouped. When multi-level logical grouping is needed, using an explicit query builder is clearer and less error-prone.

### Do not assume And/Or order matches natural reading

If the business requirement is:

~~~text
status = ACTIVE AND (category = BOOK OR category = MUSIC)
~~~

then a simple derived query name may not express the desired parenthesized grouping. Consider `In` if the two categories form a set of values:

~~~java
List<Product> findByStatusAndCategoryIn(
    String status,
    Collection<String> categories
);
~~~

Or use `CriteriaQuery`/`NativeQuery` to build boolean groups with the exact structure.

## 5. What is a property path?

A property path is the traversal path from the root entity through one or more nested properties.

Example order model:

~~~java
public class PurchaseOrder {

    private String orderNumber;
    private Customer customer;
    private Address shippingAddress;
    private Double total;
}

public class Customer {

    private String name;
    private String email;
    private String customerCode;
}

public class Address {

    private String city;
    private String postalCode;
}
~~~

From the `PurchaseOrder` entity, you can access the properties:

- `orderNumber`
- `customer.name`
- `customer.email`
- `shippingAddress.city`
- `shippingAddress.postalCode`
- `total`

A repository method can express nested paths:

~~~java
List<PurchaseOrder> findByCustomerEmail(String email);

List<PurchaseOrder> findByShippingAddressCity(String city);
~~~

Spring Data must resolve the string `CustomerEmail` into the path `customer.email` and `ShippingAddressCity` into `shippingAddress.city`.

Property path names in derived queries are based on the Java model and persistent metadata. They are not simply JSON field name strings.

## 6. Property path resolution rules

When encountering a string such as `ShippingAddressCity`, Spring Data must decide whether it is:

- A direct property named `shippingAddressCity`, or
- The property `shippingAddress` followed by the property `city`.

The property path resolution mechanism tries to find a direct property first. If none is found, it tries splitting the string at uppercase boundaries to resolve a nested path.

This can be described simply as follows:

1. Convert the leading segment into a Java-convention property name, e.g. `ShippingAddressCity` into `shippingAddressCity`.
2. Try to look up that direct property on the current entity.
3. If it does not exist, try splitting the string at camel case boundaries, starting from the split position nearest the end.
4. Check whether the head segment is a property of the current entity.
5. If found, continue resolving the remainder against the type of that property.
6. If no valid path can be found, Spring Data reports an error indicating no matching property exists.

Example:

~~~text
PurchaseOrder
    |
    +-- customer
    |      |
    |      +-- name
    |      +-- email
    |      +-- customerCode
    |
    +-- shippingAddress
    |      |
    |      +-- city
    |      +-- postalCode
    |
    +-- total
~~~

The name `findByShippingAddressCity` resolves to:

~~~text
shippingAddress.city
~~~

The name `findByCustomerEmail` resolves to:

~~~text
customer.email
~~~

### Preferring direct properties can create ambiguity

Suppose an entity has both properties:

~~~java
public class PurchaseOrder {

    private String customerEmail;
    private Customer customer;
}
~~~

and the `Customer` class has an `email` property.

The name `findByCustomerEmail` could be interpreted in two ways:

~~~text
customerEmail
customer.email
~~~

The parser prefers trying the direct property first. If the direct property exists, it may be chosen instead of the nested path.

If you want to be certain of querying `customer.email`, use an underscore to mark the boundary:

~~~java
List<PurchaseOrder> findByCustomer_Email(String email);
~~~

The underscore disambiguates the path:

~~~text
customer.email
~~~

This is an important technique for resolving cases where a property name collides with a segment of a property path.

## 7. Using underscores to explicitly mark boundaries

In Spring Data property paths, the underscore `_` is used as an explicit separator between path segments.

Examples:

~~~java
findByShippingAddress_City(String city);
findByCustomer_CustomerCode(String code);
findByCustomer_Email(String email);
~~~

Corresponding paths:

| Method fragment | Property path |
|---|---|
| `ShippingAddress_City` | `shippingAddress.city` |
| `Customer_CustomerCode` | `customer.customerCode` |
| `Customer_Email` | `customer.email` |

Use underscores when:

- The entity has a long direct property name that could cause confusion.
- A property path has multiple levels of nesting.
- The method name should clearly show the boundary between the parent object and child property.
- The parser could resolve the path in more than one way.

Three-level example:

~~~java
public class PurchaseOrder {
    private Customer customer;
}

public class Customer {
    private Address primaryAddress;
}

public class Address {
    private String postalCode;
}
~~~

You can write:

~~~java
List<PurchaseOrder> findByCustomer_PrimaryAddress_PostalCode(
    String postalCode
);
~~~

The explicit path is:

~~~text
customer.primaryAddress.postalCode
~~~

Avoid using underscores in Java property names when possible, because Spring Data reserves this character for separating property paths. Follow standard Java camelCase naming conventions.

## 8. When Java property names differ from Elasticsearch field names

An entity can use readable Java names while the Elasticsearch mapping uses different names:

~~~java
@Document(indexName = "orders")
public class PurchaseOrder {

    @Field(name = "order_number", type = FieldType.Keyword)
    private String orderNumber;

    @Field(name = "customer_name", type = FieldType.Text)
    private String customerName;
}
~~~

In the repository, derived queries use the Java properties:

~~~java
List<PurchaseOrder> findByOrderNumber(String number);

List<PurchaseOrder> findByCustomerName(String name);
~~~

Do not write:

~~~java
// Do not use Elasticsearch field names as Java property paths
findByOrder_number(String number);
findByCustomer_name(String name);
~~~

Spring Data uses persistent metadata to map Java properties to Elasticsearch field names. `@Field(name = "...")` describes the field name in the index; it does not change the property name that the query derivation parser looks for.

Distinguish the two naming layers:

| Layer | Example |
|---|---|
| Java property | `customerName` |
| Elasticsearch field | `customer_name` |
| Derived query | `findByCustomerName` |
| Query DSL after mapping | Queries field `customer_name` |

This also applies to multi-fields. If the Java property `name` has a `keyword` subfield, derived queries start from the Java property. Referencing a specific subfield in a query may require `@Query`, Criteria, or NativeQuery depending on version capabilities.

## 9. Property paths and Elasticsearch mapping types

Property path resolution and Elasticsearch field types are related but not identical concerns.

Suppose the entity has:

~~~java
public class PurchaseOrder {

    private Customer customer;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;
}
~~~

Spring Data must resolve Java paths such as `customer.email` or `lines.productCode`. Mapping metadata then indicates whether the corresponding field is stored as an object, nested, or another field type.

A valid property path does not automatically guarantee that the query has proper nested query semantics. For data declared with `FieldType.Nested`, Elasticsearch requires querying inside a nested context to preserve relationships among child objects. Whether a derived query generates a proper nested query depends on Spring Data Elasticsearch support in the version in use and the query type generated.

When complex nested queries are needed or explicit control over the nested path is required, use `NativeQuery` with nested Query DSL via `ElasticsearchOperations`. Inspect actual requests or run integration tests to confirm the query is placed in the proper nested context.

### Nested object example

~~~java
public class OrderLine {

    private String productCode;
    private Integer quantity;
}

@Document(indexName = "orders")
public class PurchaseOrder {

    @Id
    private String id;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;
}
~~~

A method name such as:

~~~java
List<PurchaseOrder> findByLines_ProductCode(String code);
~~~

indicates the Java property path is `lines.productCode`. However, if you need to guarantee that two conditions match on the same specific nested object, use an explicit nested query instead of relying on the parser to infer business intent.

## 10. Rules for Id and inherited repository methods

Spring Data repositories come with predefined methods such as `findById`. This method is meant for the entity's identifier, not merely as a derived query on a property named `id`.

Example:

~~~java
@Document(indexName = "customers")
public class Customer {

    @Id
    private String customerKey;

    private String id;
}
~~~

With a class like the above:

- `findById(id)` is the inherited method using the identifier annotated with `@Id`.
- If you want to search by a regular property named `id`, you must declare a derived method with a clearly distinct name, such as `findCustomerById`, and verify how it is parsed in your project's version.
- `findByCustomerKey` queries by the Java property `customerKey`; distinguish it from the inherited ID-lookup method.

In practice, name the `@Id` property clearly—such as `customerId` or `documentId`—to avoid colliding with another business property also named `id`.

## 11. Distinguishing valid method names from supported queries

A method name can be syntactically valid for the parser, yet the corresponding query may not be supported by Spring Data Elasticsearch in the way you expect.

There are three layers to examine:

1. **Parser:** Can Spring Data recognize the subject, predicate, operator, and property path?
2. **Query creator:** Does Spring Data Elasticsearch translate that predicate into the corresponding query?
3. **Mapping and Elasticsearch:** Does the actual field have a type compatible with the query and cluster mapping?

For example, `findByNameContaining` may be recognized by the parser, but string-matching semantics depend on field type and how Spring Data Elasticsearch implements the query. If `name` is `text`, the analyzer may split the content into tokens. If `name` is `keyword`, the string is kept as a single term. Do not assume `Containing` is always equivalent to SQL `LIKE '%value%'`.

Similarly, a method with a valid property path whose field does not exist in the actual mapping may still return empty results or fail at runtime.

Therefore, whenever a derived query yields unexpected results, inspect the parser, generated query, mapping, and indexed data in turn.

## 12. Naming rules for readability and maintainability

Several guidelines help keep repository methods clear:

**Use Java property names consistently.** Method names should reflect entity properties, not Elasticsearch snake_case field names.

**Keep methods short.** If a method name has many conditions, deep nested paths, or multiple operators, consider a query builder.

**Use underscores where path disambiguation is needed.** Do not force readers to guess whether the parser picks a direct property or a nested property.

**Use parameter types matching the properties.** If a field is `Double`, avoid passing a string; if a field is a date, use a temporal type compatible with the mapping and converter.

**Keep parameter order consistent.** Parameter order must follow the order in which conditions appear in the method name.

**Use Pageable for dynamic sorting.** Avoid creating multiple nearly identical methods that differ only in `OrderBy`.

**Do not rely on method names to replace complex Query DSL.** If you need logical parentheses, nested queries, scripts, aggregations, or Search API options, use Operations.

### Example of readable methods

~~~java
public interface PurchaseOrderRepository
        extends ElasticsearchRepository<PurchaseOrder, String> {

    List<PurchaseOrder> findByOrderNumber(String orderNumber);

    List<PurchaseOrder> findByCustomer_Email(String email);

    List<PurchaseOrder> findByShippingAddress_City(String city);

    Page<PurchaseOrder> findByStatusOrderByCreatedAtDesc(
        String status,
        Pageable pageable
    );

    long countByStatus(String status);
}
~~~

Each method describes one clear condition or goal. Nested property paths use underscores to make boundaries explicit.

## 13. Common errors in property path resolution

| Symptom | Possible cause | Resolution |
|---|---|---|
| `No property 'X' found for type 'Y'` | Property does not exist or is misspelled | Cross-check the entity and Java property names |
| Repository fails to start | Query method was parsed, but property path is invalid | Check the segment after `By` and nested paths |
| Query uses the wrong direct property | Long property name collides with a nested path | Use underscores to mark boundaries explicitly |
| Method compiles, but query is incorrect | Parser is valid, but operator semantics differ from expectations | Inspect the actual query, mapping, and supported operators |
| Nested query fails to preserve object correlation | Derived query does not create the nested context required by the use case | Use an explicit nested query via Operations |
| Elasticsearch field not found | Confusing mapping field name with Java property | Use the Java property in the method; check `@Field(name=...)` |
| ID lookup returns unexpected results | Confusing inherited `findById` with a derived property | Distinguish the `@Id` identifier from business properties |
| Query returns empty with `Containing` or `Like` | Interpreting operator using SQL semantics on text/keyword fields | Inspect the analyzer and generated query |

### No property found error

Example entity:

~~~java
public class Customer {
    private String emailAddress;
}
~~~

Repository defines:

~~~java
Optional<Customer> findByEmail(String email);
~~~

If the entity does not have an `email` property, Spring Data does not guess that `email` means `emailAddress`. Change it to:

~~~java
Optional<Customer> findByEmailAddress(String emailAddress);
~~~

Property names must match the Java model.

### Misinterpreted nested property error

Entity:

~~~java
public class Customer {
    private String addressCity;
    private Address address;
}

public class Address {
    private String city;
}
~~~

To query `address.city`, use:

~~~java
List<Customer> findByAddress_City(String city);
~~~

The underscore makes the intended path explicit and prevents the parser from preferring `addressCity`.

### Unexpected query behavior caused by analyzer

Suppose `name` is mapped as `text` with the standard analyzer. A `Containing` query may operate under Elasticsearch token semantics rather than character-by-character substring matching. If the requirement is prefix or substring search in a specific way, design an appropriate analyzer/multi-field and use the corresponding query DSL. Do not rename the method trying to force semantics incompatible with the field type.

## 14. How to inspect query derivation when debugging

When a repository method does not produce the expected results, check in order:

1. Re-read the method name and mark subject, `By`, predicate, operators, and `OrderBy`.
2. List parameters in the exact order of the conditions.
3. Open the entity and confirm each property exists.
4. For nested paths, write out the dotted path such as `customer.email`.
5. If there is any potential ambiguity, add underscores to mark boundaries.
6. Check `@Field(name = "...")`, field type, and analyzer.
7. Confirm the query method and operators are supported by your Spring Data Elasticsearch version.
8. Observe the query/request sent to Elasticsearch if results are still wrong.
9. Run the equivalent query in Elasticsearch Dev Tools against the same index.
10. Use integration tests to verify behavior against the actual mapping.

You can enable appropriate logging in development environments to observe requests. Logger names and log levels depend on the client/transport and Spring Data version. Avoid logging sensitive data or entire documents in production environments.

### Testing repository methods

An integration test should verify both direct fields and nested paths:

~~~java
@DataElasticsearchTest
class PurchaseOrderRepositoryTests {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void findsOrdersByNestedCustomerEmail() {
        // Prepare a document with a known customer.email.
        // Save the document to the test index.
        // Call findByCustomer_Email(...)
        // Assert the expected document is returned.
    }
}
~~~

This is an illustrative skeleton. Test annotations, Elasticsearch configuration, and index creation depend on your project's Spring Boot/Spring Data version. Tests should run against an Elasticsearch version compatible with the application environment and use mappings matching real use cases.

## 15. When method names are no longer the right tool

Derived queries work well when conditions are short, property names are clear, and query semantics are simple. Switch to `ElasticsearchOperations` when:

- Method names become too long or have many nested path levels.
- Complex logical grouping with explicit parentheses is required.
- Multi-level nested queries or nested correlation is needed.
- Specialized Query DSL features such as function score, geo, scripts, or rescore are required.
- Aggregations, highlighting, collapsing, or `search_after` are needed.
- Dynamic index/alias selection via `IndexCoordinates` is required.
- Queries need to combine query, sort, source filtering, and Search API options.
- Exact semantics are needed that derived operators cannot express.

For example, instead of a very long method name:

~~~java
findByStatusAndCustomer_Address_CityAndTotalGreaterThanOrPriorityTrue(...)
~~~

you can build the query using a builder:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .filter(f -> f.term(t -> t
                .field("status")
                .value("ACTIVE")
            ))
            .filter(f -> f.term(t -> t
                .field("customer.address.city")
                .value("Hanoi")
            ))
            .filter(f -> f.range(r -> r
                .number(n -> n
                    .field("total")
                    .gt(100.0)
                )
            ))
        )
    )
    .build();

SearchHits<PurchaseOrder> hits =
    operations.search(query, PurchaseOrder.class);
~~~

This illustrates explicit query expression. Builder syntax and nested queries must be adapted to your actual mapping, Java API Client, and Spring Data version. If `customer.address` is a nested field, use a nested query with the proper path instead of querying the field path as a plain object.

Operations do not replace repositories for everything. Repositories remain suitable for CRUD and simple queries; Operations are for use cases that require fine-grained control over queries and responses.

## 16. Checklist before adding a derived query method

- [ ] Does the method prefix match a supported repository form?
- [ ] Does `By` correctly mark the start of the predicate?
- [ ] Does every property in the predicate exist on the entity?
- [ ] Are property names using Java property names rather than accidentally using JSON/Elasticsearch field names?
- [ ] Are there nested property paths that should be separated with underscores?
- [ ] Does any direct property create ambiguity with a nested path?
- [ ] Are the operators supported by your project's Spring Data Elasticsearch version?
- [ ] Does parameter order match condition order?
- [ ] Do `And`/`Or` produce the intended logical grouping?
- [ ] Are `OrderBy`, `Top`, or `First` appropriate for the result requirements?
- [ ] Do the field mapping and analyzer align with the operator semantics?
- [ ] If a field is nested, does the query require an explicit nested context?
- [ ] Is the query complex enough that CriteriaQuery or NativeQuery should be used instead?

Repository method names provide a concise way to declare queries, but they rely on very specific name-parsing rules and entity metadata. Once you understand subjects, predicates, operators, and property path resolution, you can write readable derived queries, avoid name collisions, and diagnose errors quickly. When condition structures exceed what method names can clearly express, use Operations to build explicit queries and keep repositories focused on common data operations.
