# Reading Generated Query DSL and Avoiding Assumptions from JPA Behavior

Spring Data Elasticsearch lets you declare queries using repository method names, such as findByStatus or findByTitleAndCategory. This syntax feels familiar to developers coming from Spring Data JPA, but it does not mean Elasticsearch executes SQL/JPQL or preserves all JPA semantics.

A method name is a repository-level description. Spring Data parses that name, identifies properties and operators, and translates it into a query appropriate for the backing store. For Elasticsearch, the final output is an Elasticsearch Query DSL query governed by mappings, analyzers, field types, and Elasticsearch capabilities.

Therefore, when reading a derived query method, answer three questions:

1. Which conditions did Spring Data parse from the method name?
2. Which Query DSL was generated from those conditions in your running Spring Data Elasticsearch version?
3. How do the index mapping and analyzer make that Query DSL match documents?

Never assume from a method name that a query has the exact same semantics as a similar method in JPA. When behavior matters to business logic, inspect the actual Query DSL and verify against Elasticsearch.

## 1. How are repository method names parsed?

A derived query method typically has two parts:

    findByTitleAndStatusOrderByCreatedAtDesc
    |      |                         |
    |      |                         +-- ordering part
    |      +-- predicate starting after By
    +-- subject / query intent

The subject indicates the repository operation type, such as search, count, or existence check. The predicate after By describes conditions using property names and keywords such as And, Or, GreaterThan, or In. OrderBy can specify sort order.

Example:

    List<Product> findByCategoryAndActive(
        String category,
        boolean active
    );

Spring Data parses the conditions into:

- category must match the first parameter.
- active must match the second parameter.
- Both conditions are combined with AND.

Property names must match entity properties under Spring Data naming rules. If the Elasticsearch field name differs from the Java property name, mapping metadata such as @Field(name = ...) determines the actual field name used when building queries.

Example:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(name = "product_name", type = FieldType.Text)
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;

        @Field(type = FieldType.Boolean)
        private boolean active;
    }

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategoryAndActive(
            String category,
            boolean active
        );
    }

The method uses properties category and active. Field category maps under the same name; property name maps to product_name when the framework builds queries or converts documents.

Method names do not expose explicit Query DSL. To know exactly whether a method generates term, match, range, wildcard, or a specific bool structure, check the rules of your Spring Data Elasticsearch version and the mapped property types.

## 2. JPA-like syntax does not mean JPA semantics

Spring Data shares a common mechanism for parsing method names, but each datastore module provides its own query creator. JPA builds queries against relational entities and translates to JPQL/SQL. Elasticsearch builds queries around documents, inverted indexes, mappings, and Query DSL.

| Aspect | Spring Data JPA | Spring Data Elasticsearch |
|---|---|---|
| Data model | Entities and relations in a relational database | Documents and fields in an index |
| Underlying query language | JPQL/SQL | Elasticsearch Query DSL |
| Text matching | SQL predicates, LIKE, collation, or DB-specific full-text | Analyzers, term, match, phrase, wildcard, and other queries |
| Relationships | Joins, foreign keys, fetch strategies | Embedded documents, nested queries, denormalization, or multi-step queries |
| NULL / missing fields | SQL NULL and three-valued logic | Missing fields, explicit nulls, or handling via null_value mapping |
| Transactions | Can participate in database ACID transactions | No multi-document transactions equivalent to JPA |
| Sorting | By SQL columns | By sortable fields, typically keyword/numeric/date or doc values |

A method such as findByNameContaining may remind you of SQL LIKE '%value%'. However, do not assume it behaves identically on Elasticsearch. Query generation depends on supported keywords, field types, and module implementation. A wildcard query over analyzed strings behaves differently from SQL LIKE on a column value.

Likewise, IgnoreCase does not automatically guarantee case-insensitive matching across all field types. In Elasticsearch, results also depend on analyzers, normalizers, or whether the generated query supports case-insensitive options.

The safe rule is to treat method names as Spring Data declarative syntax, while Query DSL and mappings determine actual search behavior.

## 3. Common keywords and how to reason about them

Spring Data Elasticsearch supports a set of keywords for derived query methods. Supported sets and mappings can vary by version; consult documentation for your active dependency before relying on a specific keyword.

Common syntax groups:

| Group | Example method name | Repository-level meaning |
|---|---|---|
| Property match | findByStatus | Search by status |
| Combined conditions | findByStatusAndCategory | Both conditions must hold |
| Alternative conditions | findByStatusOrCategory | Either condition matches per generated query |
| Numeric/date comparison | findByPriceGreaterThan | Greater-than comparison |
| Range | findByCreatedAtBetween | Search within a range |
| Set membership | findByCategoryIn | Value belongs to a set |
| Boolean true/false | findByActiveTrue | Field equals true |
| Null check | findByDescriptionIsNull | Condition relating to fields without a value |
| Result limit | findTop10ByStatus | Limit result count |
| Sorting | findByStatusOrderByCreatedAtDesc | Sort by field |

This describes method intent. Do not treat this table as a fixed 1-to-1 mapping from keywords to a single Query DSL construct across all versions.

### And and Or

Example:

    List<Product> findByCategoryAndActive(
        String category,
        boolean active
    );

The intent is that both category and active hold. In Query DSL, AND conditions are typically expressed with a bool query containing mandatory clauses such as must or filter, depending on the generated query type.

OR method:

    List<Product> findByCategoryOrBrand(
        String category,
        String brand
    );

The intent is that either category or brand matches. In Query DSL, OR is typically expressed with bool should and an appropriate minimum_should_match. Inspect the actual query when OR is combined with AND or multiple groups, because expression grouping directly affects results.

### GreaterThan, LessThan, and Between

Comparison keywords are commonly used for numeric or date fields:

    List<Product> findByPriceGreaterThan(double price);

    List<Product> findByCreatedAtBetween(
        Instant from,
        Instant to
    );

In Elasticsearch, range conditions are typically represented with a range query. Field mappings must match the comparison type. If price is mapped as keyword, numeric range queries will not behave as intended.

### In

Method:

    List<Product> findByCategoryIn(Collection<String> categories);

expresses that category belongs to a set of values. Query DSL can use a terms-style query on an appropriate field. Field category is typically mapped as keyword to match exact category values.

### Top and First

Method:

    List<Product> findTop5ByActiveTrueOrderByCreatedAtDesc();

expresses limiting result count and sorting chronologically descending. This is a query-level result limit; do not mistake it for Elasticsearch only ever reading five documents at every execution stage.

## 4. Mapping decides query meaning

Elasticsearch does not store every string the same way. A text field is normally tokenized into tokens; a keyword field keeps values suitable for exact matching, sorting, and aggregations.

Example mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "fields": {
              "raw": {
                "type": "keyword"
              }
            }
          },
          "category": {
            "type": "keyword"
          },
          "price": {
            "type": "double"
          },
          "active": {
            "type": "boolean"
          }
        }
      }
    }

With this mapping:

- name serves analyzed text search.
- name.raw serves exact matching, sorting, or aggregation over the full name.
- category fits exact-value filtering.
- price fits range queries.
- active fits boolean conditions.

If findByName("Spring Data") translates to a term query on field name, results can differ from a match query. Text fields are split by analyzers into tokens such as spring and data; a term query does not analyze the input string like a match query.

That is why you cannot look at a method name alone and conclude it performs full-text search.

## 5. Term queries and match queries are not the same

This is one of the most critical points when reading Query DSL.

### Term query

A term query searches for an exact term in the inverted index. It does not run the analyzer over the query string like a match query.

Example:

    GET products/_search
    {
      "query": {
        "term": {
          "category": "keyboard"
        }
      }
    }

This fits a keyword field holding value keyboard.

When running a term query on a text field, you must know how the analyzer transformed content. For example, a document containing Spring Data may be indexed as tokens spring and data. A term query with literal string Spring Data will not necessarily match.

### Match query

A match query analyzes the query string using the field's search analyzer, then matches the resulting terms:

    GET products/_search
    {
      "query": {
        "match": {
          "name": "Spring Data"
        }
      }
    }

This is normally the natural choice for full-text search on text fields.

### Do not infer match solely from findBy

The method:

    List<Product> findByName(String name);

does not tell a reader with certainty that it generates a match query. If business logic requires full-text search, use an API with explicit match semantics, such as @Query with Query DSL, NativeQuery via ElasticsearchOperations, or the Java API Client directly.

@Query example:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
        List<Product> searchName(String text);
    }

Query DSL inside the annotation makes the query type explicit. Placeholder syntax and parameter serialization must follow your active Spring Data Elasticsearch version.

## 6. Containing, StartingWith, and Like are not automatically SQL LIKE

Keywords such as Containing, StartingWith, and Like easily invite comparisons to SQL LIKE. On Elasticsearch, they may map to queries matching module capabilities, such as wildcard/prefix or another query type depending on version.

Points to watch:

- Wildcard queries on keyword fields match patterns against indexed values.
- Prefix queries match terms starting with a string.
- Match queries search analyzed tokens and are not substring matches.
- N-grams or edge n-grams can enable partial-string matching, but require an analyzer configured at index time.

Prefix query example:

    GET products/_search
    {
      "query": {
        "prefix": {
          "name.raw": "key"
        }
      }
    }

Wildcard query example:

    GET products/_search
    {
      "query": {
        "wildcard": {
          "name.raw": {
            "value": "*board*"
          }
        }
      }
    }

Wildcards with a leading * are usually costlier because many terms may have to be examined. Do not write a method containing Containing and assume it is always an efficient way to do substring search over large data.

If a feature needs autocomplete, consider edge n-grams or search_as_you_type. If substring search is needed, consider n-grams and evaluate index size. Choose mappings and queries based on actual requirements rather than SQL-like method names.

## 7. Null, missing fields, and IsNull

In JPA, SQL NULL semantics are familiar to relational database users. In Elasticsearch, distinguish:

- Documents omitting the field.
- Documents having the field set to null.
- Documents holding an empty value such as string "".
- Mappings declaring null_value on certain field types.

An Elasticsearch exists query checks whether a field has an indexed value:

    GET products/_search
    {
      "query": {
        "exists": {
          "field": "description"
        }
      }
    }

Documents lacking an indexed value for description do not match exists. Plain null values likewise do not count as existing unless the mapping configures null_value appropriately.

Therefore, do not carry SQL IS NULL assumptions into Elasticsearch without checking mappings. Any IsNull or IsNotNull method, if supported by your version, should be verified to see whether it emits exists/negation or another query form.

Empty strings are not synonymous with null. If an application needs to distinguish "description not entered" from "description is empty string", define storage and query rules explicitly.

## 8. JPA entity relationships do not translate directly to Elasticsearch documents

In JPA, a query method can traverse entity associations or generate joins from relationship mappings:

    findByCustomer_Address_City(...)

Do not assume a similar property path in Spring Data Elasticsearch creates an equivalent SQL join.

Elasticsearch stores documents in JSON structures. Related data may be:

- Denormalized and copied into the same document.
- Stored inside an object field.
- Stored inside a nested field when relationships among elements of an object array must be preserved.
- Stored in separate documents and queried across multiple steps at the application layer.

### Object vs. nested differ

Consider an order with multiple line items:

    {
      "order_id": "o-101",
      "items": [
        { "sku": "A", "color": "red" },
        { "sku": "B", "color": "blue" }
      ]
    }

If items is mapped as a regular object, Elasticsearch flattens values across the object array. A query looking for sku=A and color=blue can match values drawn from different elements unless nested semantics are used.

To preserve correlation between sku and color within the same element, items needs a nested mapping and queries must use a nested query:

    GET orders/_search
    {
      "query": {
        "nested": {
          "path": "items",
          "query": {
            "bool": {
              "must": [
                { "term": { "items.sku": "A" } },
                { "term": { "items.color": "red" } }
              ]
            }
          }
        }
      }
    }

Not all derived query methods can express such complex nested queries. When queries depend on nested semantics, use explicit query APIs and inspect nested mappings.

## 9. Pageable, Sort, and result ordering

Spring Data repositories can accept Pageable or Sort:

    Page<Product> findByCategory(
        String category,
        Pageable pageable
    );

Example call:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "price")
    );

    Page<Product> page =
        productRepository.findByCategory("keyboard", pageable);

Spring Data translates pagination and sorting parameters into Elasticsearch query options. However, the sort field must have a compatible mapping.

Text fields are normally unsuitable for direct sorting because fielddata is disabled by default. For product names, sort via a keyword sub-field:

    Sort.by(Sort.Direction.ASC, "name.raw")

Numeric, date, and keyword fields normally support sorting. Verify actual field names after applying mapping metadata.

### Page and total hit counts

Page normally requires total hit counts, whereas Slice or a content-only structure may need less information. Elasticsearch has its own limits and mechanisms for total hits; counting all matches accurately can carry a cost.

Do not assume Page in Spring Data Elasticsearch has the same cost and semantics as SQL count(*) in a relational database. Check query requests, total hit tracking, and how the framework retrieves counts in your version.

For large datasets and deep pagination, from/size can become expensive. Consider search_after with a deterministic sort or an appropriate pagination strategy.

## 10. Reading the actual generated Query DSL

When a method produces surprising results, the most reliable check is inspecting the actual request sent to Elasticsearch.

Example method:

    List<Product> findByCategoryAndActive(
        String category,
        boolean active
    );

A semantically equivalent Query DSL might be:

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "category": "keyboard"
              }
            },
            {
              "term": {
                "active": true
              }
            }
          ]
        }
      }
    }

This is an illustrative example of how a filter query can be represented, not a claim that every Spring Data version emits this exact JSON for the method above. The query creator, property types, and called API can produce different structures.

To inspect requests:

1. Identify the repository method and actual arguments.
2. Identify the corresponding entity properties and post-mapping field names.
3. Inspect the field mappings in the index.
4. Enable request logging or tracing appropriate for your Spring Data/client version.
5. Capture the actual Query DSL and read each clause.
6. Use the Analyze API if the query involves text analyzers.
7. Use the Explain API to understand why a document matched or scored as it did.

Logger names and how to enable wire logging depend on client and transport versions. Refer to logging configuration for your exact dependency instead of copying logger names from an older version. Wire logging can record query bodies and sensitive data; enable it only in test environments or controlled windows.

### Validate and explain queries

You can check queries with the Validate API:

    GET products/_validate/query?explain=true
    {
      "query": {
        "match": {
          "name": "Spring Data"
        }
      }
    }

Explain API for a specific document:

    GET products/_explain/p-101
    {
      "query": {
        "match": {
          "name": "Spring Data"
        }
      }
    }

The Profile API can analyze query execution cost, though it adds overhead. Enable it only during performance investigations.

## 11. When to use @Query or NativeQuery?

Derived queries work well when conditions are simple, method names are readable, and generated queries match intent.

When queries must express Elasticsearch semantics explicitly, consider:

- @Query with JSON Query DSL for a fixed repository query.
- NativeQuery via ElasticsearchOperations when building queries flexibly using Java API Client query types.
- Elasticsearch Java Client directly when fine-grained request/response control is needed or features are not conveniently exposed by Spring Data abstractions.

@Query example for full-text search:

    @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
    List<Product> searchByNameText(String text);

NativeQuery example:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("Spring Data")
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("keyboard"))
                    )
                )
            )
        )
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

This query makes everything explicit:

- name uses a match query in query context for text search.
- category uses a term query in filter context to restrict category.
- SearchHits retains search results along with hit metadata.

NativeQuery fits when combining multiple query clauses, nested queries, aggregations, highlighting, or other Elasticsearch options that derived methods struggle to express.

## 12. Example from business requirement to Query DSL

Suppose a product listing page needs:

- Only active products.
- Only the keyboard category.
- Name content matching keyword spring.
- Products priced from 20 to 200.
- Higher priority for better name matches.
- Results ordered by relevance score.

A derived method can express the simple filter part:

    findByCategoryAndActiveAndPriceBetween(...)

However, this method does not make clear that name needs a full-text match query ranked by relevance score. You can move the query to NativeQuery:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("spring")
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("keyboard"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("active")
                        .value(FieldValue.of(true))
                    )
                )
                .filter(f -> f
                    .range(r -> r
                        .number(n -> n
                            .field("price")
                            .gte(20.0)
                            .lte(200.0)
                        )
                    )
                )
            )
        )
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

Here, business conditions are separated by role:

- match name searches text content and contributes relevance score.
- term category checks an exact category value.
- term active checks a boolean state.
- range price constrains the price interval.

The Query DSL makes clear which fields need analyzers and which need keyword/numeric/boolean mappings. This avoids expecting a method name to infer business search semantics automatically.

## 13. Testing derived queries properly

Unit tests that only check method names or mock repositories do not prove Query DSL works against real mappings. Bugs involving analyzers, field types, nested mappings, or sorting typically surface only when querying actual Elasticsearch.

An integration test should:

1. Start an Elasticsearch test instance compatible with your application dependencies.
2. Create indexes and mappings matching environment settings.
3. Index data covering both matching and non-matching cases.
4. Invoke the repository method.
5. Verify the returned document set, ordering, and counts.
6. If needed, inspect generated Query DSL or use the Explain API to verify behavior.

Sample test data:

| ID | name | category | active | price |
|---|---|---|---|---:|
| p1 | Spring Keyboard | keyboard | true | 80 |
| p2 | Spring Mouse | mouse | true | 25 |
| p3 | Mechanical Keyboard | keyboard | false | 100 |

With findByCategoryAndActive("keyboard", true), the expected match is only p1. For the test to be meaningful, however, category must be mapped as keyword and active as boolean just like in production.

For full-text search on name, verify the analyzer. For instance, a match query for spring can match Spring Keyboard; a term query on raw string spring does not share those semantics.

## 14. JPA assumptions that commonly break in Elasticsearch

### Assuming Containing is always LIKE '%value%'

SQL LIKE and inverted-index queries are two different mechanisms. Inspect actual Query DSL and consider wildcards or n-grams depending on requirements.

### Assuming findByName is always full-text search

A method name alone is not enough to conclude a query uses match. Check the generated query type and name's mapping. If full-text is needed, express match explicitly.

### Assuming IgnoreCase works across all field types

Case sensitivity depends on analyzers, normalizers, or query options. Keyword fields do not behave automatically like case-insensitive collations in a relational database.

### Assuming property traversal creates joins

Elasticsearch has no general SQL joins like JPA. Understand object/nested mappings or denormalize data.

### Assuming IsNull works like SQL NULL

Missing fields, explicit nulls, empty strings, and null_value have distinct semantics. Use exists queries and inspect mappings.

### Assuming Sort on text always works

Text fields are typically not directly sortable. Use keyword sub-fields or types with appropriate doc values.

### Assuming Page costs the same as SQL pagination

Elasticsearch has from/size limits and separate total hit costs. Deep pagination may require search_after.

### Assuming @Transactional rolls back across multiple documents

Elasticsearch does not provide multi-document transactions like JPA. Bulk requests can partially succeed and require item-level handling.

## Conclusion

Spring Data Elasticsearch derived query methods provide concise query declarations, but method names are merely inputs to the module's query creator. The actual Query DSL, mappings, and index analyzers determine which documents match, how values are compared, and how results are ordered.

Do not assume findByName equals full-text match, Containing always equals SQL LIKE, IgnoreCase always ignores case, or property traversal builds joins like JPA. For simple conditions, derived queries can suffice. For full-text, nested, wildcard, scoring, or aggregation queries, use @Query, NativeQuery, or the Elasticsearch Java Client to express Query DSL explicitly. Whenever behavior matters, inspect actual requests and test against real Elasticsearch mappings.
