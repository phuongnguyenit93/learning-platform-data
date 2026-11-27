# Declaring @Query Using MongoDB Query Expressions

## 1. Why Do We Need @Query When Derived Queries Already Exist?

In Spring Data MongoDB, a repository can generate queries from method names, such as **findByCategoryAndActive**. That approach is very convenient for simple conditions. However, when you need to combine multiple MongoDB operators such as **$or**, **$in**, **$gte**, **$elemMatch**, or query along nested document paths, method names can become long and hard to read.

The **@Query** annotation lets you write a **MongoDB query expression as a JSON-like string** directly on a repository method. As a result, you keep the repository interface concise while clearly describing the BSON condition to send to MongoDB. This is the topic **Declaring @Query Using MongoDB Query Expressions**, part of the **JSON Queries** chapter.

Within the **SPRING_DATA_MONGODB** module, @Query is one data-access-layer tool alongside **MongoTemplate**, derived queries, aggregation, and other repositories. It helps implement search requirements, but effectiveness depends on the document model, indexes, BSON types, pagination, and testing approach. The annotation does not automatically create indexes, guarantee fast queries, or replace authorization rules, transactions, or reactive processing.

Learning objectives after this lesson:

1. Know how to import and declare Spring Data MongoDB's **@Query** on a repository method.
2. Write JSON filters with MongoDB operators and **?0, ?1, ...** parameters.
3. Apply range, logical, array, embedded object, regex, and date/time conditions.
4. Use projection via **fields**, sorting, Pageable, count, and exists.
5. Understand the mapping between Java properties and BSON fields as well as null/missing issues.
6. Identify risks related to query injection, indexes, performance, and data integrity.
7. Write integration tests and cross-check queries using mongosh/MongoTemplate.

## 2. Sample Data Used Throughout

Suppose an e-commerce service has a **products** collection containing the following document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Spring Data MongoDB",
  category: "BOOK",
  priceMinor: NumberLong("159000"),
  stock: NumberInt(8),
  active: true,
  tags: ["JAVA", "SPRING", "BACKEND"],
  attributes: {
    brand: "TechBooks"
  },
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Second document in the same collection:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  sku: "PEN-002",
  name: "Note Pen",
  category: "STATIONERY",
  priceMinor: NumberLong("12000"),
  stock: NumberInt(25),
  active: true,
  tags: ["OFFICE", "SALE"],
  attributes: {
    brand: "PaperLab"
  },
  createdAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

The **priceMinor** field represents an integer in the smallest currency unit according to the system contract, not a Double. **createdAt** is a BSON Date, and **_id** is a BSON ObjectId. Using the right Java type when binding parameters helps avoid query bugs where data seems to exist but cannot be found.

Java entity mapped to the collection:

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    String category,
    long priceMinor,
    int stock,
    boolean active,
    List<String> tags,
    Attributes attributes,
    Instant createdAt
) {
    public record Attributes(String brand) {}
}
~~~

The example uses a Java record to represent an immutable entity. With Spring Data MongoDB versions that support records, the framework can materialize them from the corresponding components. What matters for this lesson is that **Java property names** match the BSON model and are used consistently in the repository.

## 3. Importing the Right @Query

The MongoDB repository query annotation is imported as:

~~~java
import org.springframework.data.mongodb.repository.Query;
~~~

Do not confuse it with annotations of the same name from JPA or other libraries. A minimal repository:

~~~java
package com.example.catalog;

import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {

    @Query("{ 'active': true }")
    List<ProductDocument> findActiveProductsJson();
}
~~~

The expression **{ 'active': true }** is a MongoDB filter: find documents where active equals Boolean true. When the method is called, Spring Data uses the metadata of **ProductDocument** to determine the products collection and converts BSON results into ProductDocument instances.

### 3.1. JSON-like Is Not an SQL String

In @Query, we write syntax based on a **MongoDB query document**, not SQL:

~~~java
@Query("{ 'category': 'BOOK', 'active': true }")
List<ProductDocument> findActiveBooks();
~~~

Equivalent condition in mongosh:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
});
~~~

The examples in this lesson use **single quotes** inside the annotation string to keep Java code readable. Spring Data MongoDB supports this JSON-like representation when parsing queries. For strict JSON tools outside the framework, double quotes are the standard JSON syntax; you should not pass the raw annotation string to another JSON parser and expect identical behavior.

### 3.2. Derived Query vs. @Query

~~~java
// Query derived from the method name.
List<ProductDocument> findByCategoryAndActive(
    String category, boolean active
);

// Query declared with MongoDB JSON.
@Query("{ 'category': ?0, 'active': ?1 }")
List<ProductDocument> findByFilterJson(
    String category, boolean active
);
~~~

Both approaches can express the same condition. If a derived query is short and easy to understand, switching to @Query is not mandatory. Use @Query when a direct MongoDB expression is **clearer** or requires capabilities beyond method naming.

## 4. Binding Parameters with ?0, ?1, ...

In @Query, **?0** is the first parameter of the method, **?1** is the second parameter, indexed from **0**:

~~~java
@Query("{ 'category': ?0, 'active': ?1 }")
List<ProductDocument> findInCategory(
    String category, boolean active
);
~~~

Example:

~~~java
List<ProductDocument> books =
    repository.findInCategory("BOOK", true);
~~~

Spring Data binds the parameter values with the appropriate types and builds the equivalent condition:

~~~javascript
db.products.find({
  category: "BOOK",
  active: true
});
~~~

### 4.1. Do Not Put Placeholders Inside Value Quotes

**Correct:**

~~~java
@Query("{ 'sku': ?0 }")
List<ProductDocument> findBySkuJson(String sku);
~~~

**Do not write:**

~~~java
// Wrong example: easily turns ?0 into part of a string literal.
@Query("{ 'sku': '?0' }")
List<ProductDocument> findBySkuWrong(String sku);
~~~

Parameter values are bound and converted by the framework, not spliced as raw text into the query string. Placing the placeholder outside quotes lets the binding mechanism handle String, Number, Boolean, ObjectId, and other types as intended.

### 4.2. Why Not Concatenate User-Provided Strings?

Do not build a JSON query by directly concatenating input:

~~~java
// Avoid: code illustrating an unsafe way to build a query.
String raw = "{ 'sku': '" + userInput + "' }";
~~~

This risks producing invalid syntax, creating query injection, and making BSON type checking difficult. With repositories, use **?0, ?1** to pass values as data. Spring Data provides a binding and escaping mechanism for String parameters in normal query structures, rather than letting them arbitrarily alter JSON query operators.

However, **safe binding does not mean every input value is safe from a business or resource standpoint**. A user-controlled regex can still be overly CPU-expensive; an $in list with hundreds of thousands of elements can still create a heavy query. You still need to enforce length, count, and appropriate limits.

## 5. Comparison Operators: $gt, $gte, $lt, $lte

In mongosh, a condition where price falls within a range:

~~~javascript
db.products.find({
  priceMinor: { $gte: NumberLong("10000"), $lte: NumberLong("200000") }
});
~~~

In the repository:

~~~java
@Query("{ 'priceMinor': { '$gte': ?0, '$lte': ?1 } }")
List<ProductDocument> findPriceBetweenJson(
    long minimumMinor,
    long maximumMinor
);
~~~

Call example:

~~~java
List<ProductDocument> result =
    repository.findPriceBetweenJson(10_000L, 200_000L);
~~~

| Operator | Meaning | Example |
| --- | --- | --- |
| $gt | Greater than | stock greater than 0 |
| $gte | Greater than or equal to | priceMinor at least 10,000 |
| $lt | Less than | stock less than 5 |
| $lte | Less than or equal to | priceMinor at most 200,000 |
| $ne | Not equal to | category different from BOOK |

Pay attention to **data types and units**: priceMinor is a long, so accept a long parameter. If the client sends an amount in another unit, convert/validate it at the business layer before calling the repository. Do not use Double for money just because API JSON uses numbers.

### 5.1. Combining Conditions Across Fields

~~~java
@Query("{ 'active': true, 'stock': { '$gt': 0 }, 'priceMinor': { '$lte': ?0 } }")
List<ProductDocument> findAvailableUnder(long maximumMinor);
~~~

Multiple fields at the same level in a filter are typically combined with **AND**. This condition finds products that are active, in stock, and within the price cap.

### 5.2. A Common Logic Mistake

If the user enters **minimumMinor** greater than **maximumMinor**, the query cannot match any valid value. The repository does not automatically fix an inverted range. You should validate:

~~~java
if (minimumMinor < 0 || maximumMinor < minimumMinor) {
    throw new IllegalArgumentException("Invalid price range");
}
~~~

That is a service-layer rule, not a feature of @Query.

## 6. Logical Operators: $and, $or, $nor

MongoDB supports combining conditions:

~~~java
@Query("""
       {
         '$and': [
           { 'active': true },
           {
             '$or': [
               { 'category': ?0 },
               { 'tags': ?1 }
             ]
           }
         ]
       }
       """)
List<ProductDocument> findActiveCategoryOrTag(
    String category,
    String tag
);
~~~

The example uses a **Java text block** (Java 15+) to display JSON clearly; projects using older Java versions can write the entire string on a single line. Spring Data binds placeholders in the query string after Java supplies the annotation value.

The condition finds active products that also belong to either group:

- category matches the passed value;
- **or** the tags array contains the passed tag.

In MongoDB, the condition **{ tags: "JAVA" }** can match documents where tags is an array containing the element "JAVA", without needing $elemMatch for that simple comparison.

### 6.1. When Is an Explicit $and Needed?

For two conditions on different fields at the same level, a single JSON object already expresses AND:

~~~java
@Query("{ 'active': true, 'category': ?0 }")
List<ProductDocument> activeCategory(String category);
~~~

Use $and when a complex structure needs to combine expressions with duplicate keys or clearly group multiple $or branches. Do not write a JSON object with **two duplicate $or keys** expecting both to apply; the parser may keep one key and discard the other. Write $and containing two separate $or objects.

### 6.2. Using $nor

~~~java
@Query("{ '$nor': [ { 'category': 'DISCONTINUED' }, { 'active': false } ] }")
List<ProductDocument> findNotDiscontinuedAndNotInactive();
~~~

Logically, $nor matches when **none** of the branches are true. However, when data has missing/null fields, negation semantics may differ from expectations. You should check legacy data and use a clearer direct filter if possible.

## 7. Array Queries: $in, $nin, $all, and $elemMatch

### 7.1. $in: Belonging to a Set of Values

~~~java
import java.util.Collection;

@Query("{ 'category': { '$in': ?0 }, 'active': true }")
List<ProductDocument> findActiveInCategories(
    Collection<String> categories
);
~~~

Called with:

~~~java
List<ProductDocument> result = repository.findActiveInCategories(
    java.util.List.of("BOOK", "STATIONERY")
);
~~~

In MongoDB, the equivalent condition:

~~~javascript
db.products.find({
  category: { $in: ["BOOK", "STATIONERY"] },
  active: true
});
~~~

**$nin** is the negation of $in according to MongoDB rules, and you must note that documents missing the field can also match the negated condition. Do not use $nin without checking the policy for missing fields.

### 7.2. $all: Containing All Required Tags

~~~java
@Query("{ 'tags': { '$all': ?0 } }")
List<ProductDocument> findWithAllTags(
    java.util.Collection<String> requiredTags
);
~~~

If "JAVA" and "SPRING" are passed, the document must contain both tags. Unlike comparing tags against a single String, this check requires multiple elements to be present.

### 7.3. $elemMatch for an Array of Documents

Suppose actual data has:

~~~javascript
{
  sku: "KIT-001",
  variants: [
    { color: "RED", stock: NumberInt(0) },
    { color: "BLUE", stock: NumberInt(5) }
  ]
}
~~~

If you need **a single variants element that both has color RED and stock greater than 0**, use $elemMatch:

~~~java
@Query("{ 'variants': { '$elemMatch': { 'color': ?0, 'stock': { '$gt': ?1 } } } }")
List<ProductDocument> findVariantWithStock(
    String color,
    int minimumExclusiveStock
);
~~~

This example method requires a domain with a corresponding **variants** property; the ProductDocument in the opening example did not declare this field, so this is a query pattern for extending the domain when product variants exist.

**Why is $elemMatch important?** Two independent conditions on an array path can be satisfied by **two different elements**. $elemMatch ensures the conditions apply within **the same element**.

## 8. Querying Fields of Embedded Objects

The sample document has:

~~~javascript
{
  attributes: {
    brand: "TechBooks"
  }
}
~~~

To find products by brand:

~~~java
@Query("{ 'attributes.brand': ?0 }")
List<ProductDocument> findByBrandJson(String brand);
~~~

**attributes.brand** is a MongoDB dot-notation path. This field is searched inside the embedded attributes object, **not another collection**.

If an older schema stored attributes as a String or omitted attributes, the query may fail to find those documents. @Query does not automatically normalize different schema versions; migration or an intentional compatibility condition is required.

### 8.1. When Using @Field to Rename BSON Fields

Suppose Java has property **postalCode** while MongoDB stores **postal_code**, declared as:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

public record Address(
    String city,
    @Field("postal_code") String postalCode
) {}
~~~

For queries mapped by Spring Data through entity metadata, QueryMapper can translate the property path to the corresponding BSON field name. When writing **mongosh or raw driver** queries, you must always use the actual BSON name, such as **address.postal_code**.

When using JSON @Query on entities with many @Field annotations, verify the actual mapped query in a test environment. Do not assume every arbitrary property path string, complex alias, or custom converter will be translated as intended. Standardize naming conventions and use tests to catch drift between Java and BSON.

## 9. Missing Data, Null, and BSON Types

MongoDB distinguishes between **a field not existing**, **a field existing with null**, and **a field having a value**. Those distinctions matter greatly when writing filters.

~~~java
// Find documents completely missing the attributes.brand field.
@Query("{ 'attributes.brand': { '$exists': false } }")
List<ProductDocument> findMissingBrand();

// A null condition in MongoDB can match both null and missing.
@Query("{ 'attributes.brand': null }")
List<ProductDocument> findNullOrMissingBrand();
~~~

If the business requires finding **a field that exists and has value null**, use a two-part condition:

~~~java
@Query("{ 'attributes.brand': { '$exists': true, '$eq': null } }")
List<ProductDocument> findExplicitNullBrand();
~~~

In the mongo shell:

~~~javascript
db.products.find({
  "attributes.brand": { $exists: true, $eq: null }
});
~~~

### 9.1. Checking Types with $type

~~~java
@Query("{ 'priceMinor': { '$type': 'long' } }")
List<ProductDocument> findProductsWithLongPrice();
~~~

Here **long** is the BSON Int64 type name, different from a String containing digits. Type-based queries can be useful in migration diagnostics, but **should not be turned into permanent business logic** if the data should be normalized to a single schema.

Checking in mongosh:

~~~javascript
db.products.aggregate([
  {
    $project: {
      sku: 1,
      priceType: { $type: "$priceMinor" },
      createdAtType: { $type: "$createdAt" }
    }
  }
]);
~~~

If the same field has documents storing priceMinor as String, Int32, and Int64, comparisons may yield unexpected results. Fix the data or standardize the type instead of simply casting every input parameter to String.

## 10. ObjectId and Time Parameters

### 10.1. Comparing by ObjectId

The entity has **@Id ObjectId id**, and the repository already has findById. When you need additional conditions:

~~~java
import org.bson.types.ObjectId;

@Query("{ '_id': ?0, 'active': true }")
java.util.Optional<ProductDocument> findActiveByIdJson(ObjectId id);
~~~

The first parameter is **ObjectId**, not an arbitrary hex string. If the API receives an ID as a String, convert/validate it first:

~~~java
ObjectId id = new ObjectId(hexId);
java.util.Optional<ProductDocument> found =
    repository.findActiveByIdJson(id);
~~~

If the collection actually stores _id as BSON String, you must adjust the mapping and binding accordingly. Printing ObjectId as a 24-character hex string does not mean String and BSON ObjectId have the same type.

### 10.2. Querying by Time

The document has createdAt as BSON Date, while Java uses **Instant**:

~~~java
import java.time.Instant;

@Query("{ 'createdAt': { '$gte': ?0, '$lt': ?1 } }")
List<ProductDocument> findCreatedInRange(
    Instant startInclusive,
    Instant endExclusive
);
~~~

Using the half-open interval **[start, end)** avoids duplicate records across adjacent intervals:

~~~java
Instant start = Instant.parse("2025-06-01T00:00:00Z");
Instant end = Instant.parse("2025-07-01T00:00:00Z");

List<ProductDocument> createdInJune =
    repository.findCreatedInRange(start, end);
~~~

Keep timezones consistent when converting API inputs and compare in UTC/Instant. If BSON stores dates as ISO Strings instead of Date, querying with Instant may not work according to the expected contract.

## 11. Regex and String Search

MongoDB supports regular expressions via **$regex**:

~~~java
@Query("{ 'name': { '$regex': ?0, '$options': 'i' } }")
List<ProductDocument> searchNameByRegex(String regexPattern);
~~~

Example passing a pattern starting with **Spring**:

~~~java
List<ProductDocument> matches =
    repository.searchNameByRegex("^Spring");
~~~

**Note:** When a parameter has regex semantics, users can influence expression complexity. You should not pass an unbounded regex directly into a production query. If the intent is only literal text search, **escape regex metacharacters** and limit length, results, and execution time.

Another way to keep the distinction in mind:

~~~java
// A regular String is compared by exact value.
@Query("{ 'name': ?0 }")
List<ProductDocument> findExactName(String name);
~~~

findExactName looks up the exact name value under query comparison rules and does not turn the parameter into a regex. If the application requires full-text search, autocomplete, accent-insensitive search, or relevance ranking, consider appropriate indexes and search engines rather than assuming $regex handles every need well.

### 11.1. Regex Performance

Expressions with a prefix anchored at the start of the string can use indexes more effectively in some cases. Conversely, regexes with leading wildcards or case-insensitive regexes can struggle to leverage standard indexes. Behavior depends on index, collation, pattern, and server version; you must **measure with explain**, not conclude from syntax alone.

## 12. Returning a Subset of Fields with fields

If a list screen only needs name and price, there is no need to read the entire document.

The @Query annotation has a **fields** attribute to declare projection on the MongoDB side:

~~~java
public interface ProductSummary {
    ObjectId getId();
    String getName();
    long getPriceMinor();
}
~~~

Repository:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ '_id': 1, 'name': 1, 'priceMinor': 1 }"
)
List<ProductSummary> findActiveSummaries();
~~~

The result only needs the projected fields, after which Spring Data can map them to the **interface projection** ProductSummary. Returning a dedicated interface keeps consuming code from assuming unloaded fields are present.

### 12.1. Include and Exclude

In MongoDB, projection follows rules:

- Value **1** typically indicates the field is kept.
- Value **0** typically indicates the field is excluded from the result.
- Aside from the **_id** exception, you cannot arbitrarily mix include and exclude in a standard projection.

Example without needing the ID:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ '_id': 0, 'name': 1, 'priceMinor': 1 }"
)
List<ProductSummary> findSummariesWithoutId();
~~~

In that case, **getId()** has no data to return; in a real application, design a projection interface without id or accept null according to contract. When an endpoint needs a product detail link, keep _id.

### 12.2. Avoid Returning a Full Entity After Partial Projection

~~~java
// Discouraged if callers treat the result as a complete ProductDocument.
@Query(
    value = "{ 'active': true }",
    fields = "{ 'name': 1 }"
)
List<ProductDocument> findPartialProducts();
~~~

If only name is loaded while requiring materialization of ProductDocument with primitives long, int, boolean, and other constructor fields, the object may have nulls, default values, or materialization errors depending on mapping. Worse, code might pass that field-missing object to save as if it were a full entity and lose data.

**Best practice:** use a **matching DTO/projection** for the exact loaded fields and never save back an entity read from a partial projection.

## 13. Sorting and Pagination

Queries can return many results. Production APIs need a cap on returned count and a clear order.

### 13.1. Fixed Sort in the Annotation

~~~java
@Query(
    value = "{ 'active': ?0 }",
    sort = "{ 'createdAt': -1, '_id': -1 }"
)
List<ProductDocument> findActiveNewestFirst(boolean active);
~~~

In MongoDB, **-1** means descending order. Adding _id as a secondary key makes ordering more deterministic when multiple products share the same createdAt.

### 13.2. Caller-Supplied Sort

~~~java
import org.springframework.data.domain.Sort;

@Query("{ 'active': ?0 }")
List<ProductDocument> findActiveSorted(
    boolean active,
    Sort sort
);
~~~

Example:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);

List<ProductDocument> result =
    repository.findActiveSorted(true, sort);
~~~

Spring Data treats **Sort** as a special parameter, not a parameter bound into the JSON filter. When sorting by id, mapping metadata can translate the Java property id into BSON _id.

If clients are allowed to choose sort field names, use an **allowlist of permitted field names**, rather than accepting any arbitrary string without validation. Sorting on unindexed fields or unbounded datasets can cause expensive queries.

### 13.3. Pagination with Pageable

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query("{ 'active': ?0 }")
Page<ProductDocument> findActivePage(
    boolean active,
    Pageable pageable
);
~~~

Calling it:

~~~java
Pageable pageRequest = org.springframework.data.domain.PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
);

Page<ProductDocument> page =
    repository.findActivePage(true, pageRequest);
~~~

**Page** may require a count query to determine the total number of elements; this can be costly on large collections or complex conditions. If the client only needs to know whether a next page exists, consider **Slice** or keyset pagination where appropriate. Passing Pageable does not automatically create indexes or make skip/limit with large offsets free.

### 13.4. Ensuring Stable Ordering

If you only sort by createdAt and multiple documents share the same timestamp, results across pages may duplicate or skip items when data changes during pagination. Adding a unique key such as _id to the sort helps keep ordering deterministic; for frequently written data, you still need a pagination strategy suited to your consistency requirements.

## 14. Count and Exists with @Query

Beyond returning documents, the annotation can request count or exists results:

~~~java
@Query(value = "{ 'category': ?0, 'active': true }", count = true)
long countActiveByCategoryJson(String category);
~~~

~~~java
@Query(value = "{ 'sku': ?0 }", exists = true)
boolean existsBySkuJson(String sku);
~~~

Comparison:

| Query | Result |
| --- | --- |
| findBySkuJson | List or domain object matching the declared method. |
| countActiveByCategoryJson | Number of documents satisfying the condition. |
| existsBySkuJson | true if a matching document exists, false otherwise. |

An exists query is suitable for simple existence checks, but **checking exists before inserting does not replace a unique index**. Two concurrent requests can both see that an sku does not yet exist and both try to insert. If SKU must be unique, enforce a unique index in MongoDB and handle duplicate key errors.

### 14.1. @Query Is Not a General-Purpose API for All Updates

@Query primarily describes filters and repository query shapes. Some versions allow declaring delete queries via a dedicated option, but **@Query(value=...)** should not be treated as an arbitrary update command.

When you need conditional field updates, use MongoTemplate with **Query/Update**, supported repository update methods, or a mechanism suited to your Spring Data version. When multi-stage aggregation is needed, use **@Aggregation** or MongoTemplate.aggregate rather than cramming an aggregation pipeline into @Query.

## 15. When to Use @Query, Derived Queries, MongoTemplate, or Aggregation?

| Need | Suggested Choice | Reason |
| --- | --- | --- |
| Find by category and active | Derived query or @Query | Both are simple; prefer whichever is easier to read. |
| Filter with multiple $or, $in, ranges | @Query | Clearly expresses MongoDB structure in the repository. |
| Flexible conditions with many optional parameters | MongoTemplate + Criteria, or query builder | Avoids a JSON string with many hard-to-manage branches. |
| Partial document updates | MongoTemplate.updateFirst/updateMulti or appropriate update API | A @Query filter is not itself an update command. |
| Grouping data, $lookup, $group, $project | Aggregation/@Aggregation | This is a pipeline, not a simple find filter. |
| Retrieving a fixed set of fields | @Query(fields=...) + projection | Reduces transferred/mapped data. |
| Non-blocking interaction | ReactiveMongoRepository/ReactiveMongoTemplate | Uses the appropriate reactive stream. |

In large applications, choosing one API does not necessarily exclude the others. A single repository can provide simple derived queries and @Query for complex conditions; flexible aggregation or update tasks can live in a custom repository using MongoTemplate.

## 16. Performance: From @Query to Indexes

A readable repository method does not guarantee the query runs fast. Example filter:

~~~java
@Query("{ 'category': ?0, 'active': true }")
List<ProductDocument> findActiveByCategory(String category);
~~~

If this query is on a hot API path, you can evaluate an index:

~~~javascript
db.products.createIndex({ category: 1, active: 1 });

db.products.find({
  category: "BOOK",
  active: true
}).explain("executionStats");
~~~

If the read path also sorts by createdAt descending, consider a compound index matching the actual filter and sort pattern:

~~~javascript
db.products.createIndex({
  category: 1,
  active: 1,
  createdAt: -1,
  _id: -1
});

db.products.find({
  category: "BOOK",
  active: true
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

The second index is only a **candidate** for a specific query pattern, not a mandatory index every products collection needs. Adding more indexes increases write cost, storage, and maintenance overhead. You must evaluate based on real workload and explain query plans.

### 16.1. What Should You Read in executionStats?

- **winningPlan**: whether an appropriate index is used or a collection scan occurred.
- **totalKeysExamined** and **totalDocsExamined**: amount of index keys/documents scanned.
- **nReturned**: number of documents returned.
- **executionTimeMillis**: execution time under observed conditions.
- **SORT stage**: whether an additional in-memory sort outside the index is required.

A good plan is not just "having IXSCAN"; it must be proportionate in scanned records, returned records, latency, and query selectivity.

### 16.2. Sources of Slow Queries

1. **$or** with multiple branches not supported by appropriate indexes.
2. **$in** containing too many elements.
3. **Regex** unable to use indexes effectively or overly complex.
4. **Pageable with large offsets** forcing the server to skip many results.
5. **fields projection** selecting too many fields or returning full entities when only a few fields are needed.
6. **Sort** without a suitable index.
7. Data with **inconsistent BSON types**, causing filters not to match the actual schema.

When diagnosing, inspect the **actual MongoDB query** along with data and indexes, rather than inferring from method names or the presence of @Query.

## 17. Protecting the Query Contract and Authorization

### 17.1. @Query Does Not Automatically Filter Tenants

If products has a **tenantId** field, a method like:

~~~java
@Query("{ 'active': true }")
List<ProductDocument> findAllActive();
~~~

can read products across every tenant that the MongoDB account is allowed to read. @Query does not automatically add a tenantId condition. In multi-tenant systems, enforce a consistent policy at the service/repository/permission layers and test queries with data from multiple tenants.

With a dedicated repository method:

~~~java
@Query("{ 'tenantId': ?0, 'active': true }")
List<ProductDocument> findActiveForTenant(String tenantId);
~~~

This example only applies when the ProductDocument schema is actually extended with tenantId and all read/write paths follow the tenant policy. Letting callers choose any tenantId arbitrarily is still not authorization; the service must obtain and verify the tenant from an authenticated context.

### 17.2. Limiting Result Counts

Do not let an API return an entire large collection just because a repository method declares **List<ProductDocument>**. Consider:

- Pageable or limiting record counts at the query layer.
- Selecting only required fields.
- Setting infrastructure timeouts/limits and monitoring latency.
- Using appropriate batch processing or cursors for long reports.

### 17.3. JSON Binding and SpEL

Spring Data MongoDB supports expression features in certain query contexts, including **SpEL** according to the syntax supported by the library version. SpEL is flexible but widens the surface area to control: do not turn user input into **part of the query structure** without validation. For most queries, **?0, ?1** are easier to read, easier to test, and less error-prone.

## 18. Integration Testing @Query

Unit tests that merely mock ProductRepository do not prove the JSON filter is parsed properly by Spring Data or that BSON is bound with the right types. You need to test against a real test-environment MongoDB (such as Testcontainers) with controlled documents.

A test repository with methods:

~~~java
public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {

    @Query("{ 'category': ?0, 'active': ?1 }")
    List<ProductDocument> findInCategory(String category, boolean active);

    @Query("{ 'priceMinor': { '$gte': ?0, '$lte': ?1 } }")
    List<ProductDocument> findPriceBetweenJson(long min, long max);

    @Query("{ 'attributes.brand': ?0 }")
    List<ProductDocument> findByBrandJson(String brand);

    @Query(value = "{ 'sku': ?0 }", exists = true)
    boolean existsBySkuJson(String sku);
}
~~~

JUnit 5 test example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;

@DataMongoTest
class ProductJsonQueryTest {

    @Autowired
    private ProductRepository products;

    @Test
    void queryBindsValuesAndNestedPath() {
        String sku = "TEST-" + UUID.randomUUID();

        ProductDocument inserted = products.insert(
            new ProductDocument(
                null,
                sku,
                "Learning MongoDB",
                "BOOK",
                159_000L,
                3,
                true,
                List.of("JAVA", "SPRING"),
                new ProductDocument.Attributes("TechBooks"),
                Instant.parse("2025-06-01T09:00:00Z")
            )
        );

        ObjectId id = inserted.id();
        assertThat(id).isNotNull();

        try {
            assertThat(products.existsBySkuJson(sku)).isTrue();

            assertThat(products.findInCategory("BOOK", true))
                .anyMatch(p -> p.id().equals(id));

            assertThat(products.findPriceBetweenJson(150_000L, 160_000L))
                .anyMatch(p -> p.id().equals(id));

            assertThat(products.findByBrandJson("TechBooks"))
                .anyMatch(p -> p.id().equals(id));
        } finally {
            products.deleteById(id);
        }
    }
}
~~~

Because the repository queries a shared collection, the test uses a random SKU to avoid colliding with other data. However, category/price/brand assertions may return multiple documents; the test checks that the newly inserted record is present in the results rather than assuming the collection contains only one document.

In practice, use a **dedicated test database** and well-scoped fixtures; if you want to assert exact counts, isolate data so results do not depend on tests running in parallel.

### 18.1. Which Cases Should Be Tested?

| Case | Expectation |
| --- | --- |
| Bind String and Boolean via ?0/?1 | Query finds the exact matching documents. |
| Bind long for priceMinor | Range filter uses the right unit and type. |
| Query attributes.brand | Reads the embedded field accurately. |
| $in with a list of categories | Returns categories belonging to the supplied set. |
| $all on tags | Requires all tags to be present. |
| Null and missing | Distinguished when business logic requires it. |
| ObjectId from API | Converted/validated before binding. |
| Projection fields | Relies only on loaded properties; does not save partial entities. |
| Sort/Pageable | Deterministic order, bounded page size, and appropriate metadata. |
| count/exists | Returns correct numeric/Boolean types and handles empty results. |
| User-supplied regex | Bounded or escaped according to contract. |
| Multi-tenant | Never returns documents from another tenant. |
| Indexes on critical queries | explain shows a plan suitable for the workload. |

## 19. Common Mistakes

| Symptom | Possible Cause | How to Check and Fix |
| --- | --- | --- |
| Repository fails to start | Invalid JSON query syntax or invalid method/property | Check the @Query string, braces, and parser error message. |
| Query misses expected String | Quotes around placeholder or mismatched type/value | Use ?0 properly; inspect BSON and binding. |
| ObjectId looks right but does not match | String and BSON ObjectId are different types | Inspect actual _id; parse or map the ID properly. |
| Price range returns unexpected results | Wrong currency unit, BSON type, or comparison operator | Check priceMinor, type, and long parameter. |
| $or applies only one branch | Duplicate $or keys inside the same object | Use $and combining separate $or objects. |
| Array query matches unintended elements | Missing $elemMatch for same-item conditions | Use $elemMatch when one element must satisfy all criteria. |
| Nested field does not match | Wrong dot path, @Field alias, or legacy schema | Inspect actual BSON and mapping metadata. |
| Projection returns null/default values | fields did not load enough for the entity | Use an appropriate DTO/interface projection. |
| Regex slows down the API | Complex pattern or unable to use index | Limit regex, inspect explain, consider search indexes. |
| Pageable is slow on deep pages | Large skip or unoptimized sort | Measure query, consider keyset pagination. |
| count is too slow | Complex query/count on a large dataset | Evaluate Slice and whether total count is truly needed. |
| Another tenant's data appears in results | Filter missing tenantId | Enforce tenant constraints on all query paths and test. |
| Derived query and @Query differ | Different filter, field name, sort, or null semantics | Compare actual queries on the same fixture. |

### 19.1. Diagnostic Workflow

1. Confirm the database and collection actually used by the repository.
2. Read the exact @Query expression, parameter count, and **?0, ?1** order.
3. Verify passed data types (ObjectId, String, long, Instant, Collection).
4. Inspect real BSON documents, including missing/null fields, arrays, and embedded objects.
5. Run the equivalent filter in mongosh and compare returned documents.
6. Check projection, sort, Pageable, count/exists, and tenant conditions.
7. For slow queries, run **explain("executionStats")** and examine indexes/workload; do not judge from annotation line count alone.
8. Add a regression test with a fixture reproducing the bug.

## 20. Practice Exercises

### Exercise 1: Binding Two Parameters

Write a repository method taking category and active to find matching products.

**Suggested Answer:**

~~~java
@Query("{ 'category': ?0, 'active': ?1 }")
List<ProductDocument> findByCategoryAndState(
    String category, boolean active
);
~~~

### Exercise 2: Price Range

Find products priced from 20,000 up to under 100,000 smallest currency units. Why would using $lte for the upper bound be wrong?

**Suggested Answer:** use **$gte: ?0** and **$lt: ?1**, with parameters 20_000L and 100_000L. If $lte is used, a price equal to 100,000 would also be returned, violating the requirement of under 100,000.

### Exercise 3: Array Query

Find products containing both JAVA and SPRING tags. Should you use $in or $all?

**Answer:** use **$all**, because $in only requires at least one value in the set; $all requires all required values to be present.

### Exercise 4: Finding Missing Fields

Find products that do not have attributes.brand yet, excluding documents where brand = null. Which condition should you use?

**Answer:** use **{ 'attributes.brand': { '$exists': false } }** to find missing fields. Comparing equal to null can match both missing and null, so it does not satisfy the distinction requirement.

### Exercise 5: Projection

A list API only needs id, name, and priceMinor. Should you use fields to fetch only name and return the full ProductDocument?

**Answer:** no. Use fields selecting **_id, name, priceMinor** and a matching DTO/interface projection. Returning a full entity from truncated data can easily cause errors or data loss if subsequent code saves it.

### Exercise 6: Name Search

A client enters arbitrary characters, and the API passes them directly into $regex. State two risks and how to improve it.

**Suggested Answer:** regex metacharacters can alter search semantics; complex regexes can consume excessive CPU or fail to use indexes. Limit length, escape characters for literal searches, limit results, and consider a more suitable search feature.

### Exercise 7: Index for Filter and Sort

The API frequently filters category = BOOK, active = true, and sorts by createdAt descending. Propose an index to evaluate and how to verify it.

**Suggested Answer:** test a compound index on **category, active, createdAt**, optionally adding _id as the secondary sort key. Run the same filter/sort with explain("executionStats"), comparing nReturned, keys/docs examined, sort stages, and index maintenance cost.

### Exercise 8: Queries and Tenants

In a multi-tenant system, a repository has a @Query method filtering only by active. Why might it be unsafe even though placeholders are bound properly?

**Answer:** because tenant filtering and access control are missing. Proper binding only secures parameter value passing; it does not enforce data-isolation policies. Verified tenant filters and consistent safeguards across all access paths are required.

## 21. Key Takeaways

1. **Spring Data MongoDB's @Query** lets you declare JSON-like MongoDB filters directly in repositories.
2. **?0, ?1... are 0-based positional placeholders**; do not concatenate raw input into JSON and do not wrap placeholders in quotes as literals.
3. **MongoDB operators keep their standard meaning**: $gte/$lt for ranges, $or/$and for logic, $in/$all/$elemMatch for arrays.
4. **BSON types determine matchability**. ObjectId differs from String; Instant must map properly to BSON Date; money must use consistent units and numeric types.
5. **@Query(fields=...) works well for projections**, but never save back a partially loaded entity.
6. **Sort and Pageable require limits and suitable indexes**. Page/count carry costs; regex and large $in lists must also be controlled.
7. **Count and exists do not replace data constraints** such as unique indexes or tenant security policies.
8. **MongoTemplate and aggregation complement @Query** when dynamic filters, updates, or data-processing pipelines are needed.
9. **Test on MongoDB and use explain** to verify results, performance, field mapping, and legacy cases.

Mastering **declaring @Query with MongoDB query expressions** helps **SPRING_DATA_MONGODB** services build repositories with clear search criteria, properly typed parameter binding, and maintainable testing, index optimization, and query diagnostics across synchronous or reactive data-access flows.
