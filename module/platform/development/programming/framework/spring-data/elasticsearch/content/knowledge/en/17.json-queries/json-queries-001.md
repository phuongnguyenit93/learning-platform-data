# StringQuery and JSON Query DSL Representation

## 1. What Is StringQuery in Spring Data Elasticsearch?

Spring Data Elasticsearch provides `Query` as an abstraction for describing search criteria. One of the implementations of this abstraction is **`StringQuery`**: a class that accepts a JSON string containing Elasticsearch Query DSL and turns it into a query that `ElasticsearchOperations` can execute.

`StringQuery` is suitable when:

- You already have Query DSL from Elasticsearch documentation or from another system.
- The search criteria have a clear structure and you want to represent them close to an Elasticsearch JSON request.
- The Criteria API does not conveniently express certain query structures.
- You want fine-grained control over clauses such as `bool`, `must`, `filter`, `nested`, `range`, or `multi_match`.

Simple example:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

Query query = new StringQuery("""
{
  "match": {
    "firstName": {
      "query": "Jack"
    }
  }
}
""");
~~~

The JSON string above is an Elasticsearch query clause. Spring Data uses that query when sending the search operation.

Point to remember: the argument to `StringQuery` is the **Query DSL section**, such as a `match` or `bool` object. Do not wrap it in an extra `"query"` layer as in the full request body of the `_search` endpoint.

## 2. What Is Query DSL?

Elasticsearch Query DSL is a JSON-based query language. A query describes the conditions that a document must meet to be returned. Queries can be nested to build complex criteria.

A full REST search request typically looks like this:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless headphones"
    }
  },
  "from": 0,
  "size": 20,
  "sort": [
    {
      "price": "asc"
    }
  ]
}
~~~

In the request above:

- `query` contains the search condition.
- `from` and `size` specify the starting offset and number of results.
- `sort` specifies the order of results.

When using `StringQuery`, pass only the contents of the `query` section:

~~~json
{
  "match": {
    "name": "wireless headphones"
  }
}
~~~

`from`, `size`, `sort`, source filtering, and other execution options are configured through properties on the Spring Data `Query` object, such as `Pageable` or `Sort`.

This distinction helps avoid a common mistake: passing the entire request body containing `"query"` into `StringQuery`, which causes Spring Data to treat that object as a query clause instead of the inner content of the request's `query` field.

## 3. Basic Structure of a JSON Query

A query clause typically has the form:

~~~json
{
  "query_name": {
    "field_name": "value"
  }
}
~~~

Example:

~~~json
{
  "term": {
    "category": "audio"
  }
}
~~~

Here:

- `term` is the query type.
- `category` is the field to search.
- `audio` is the value to match.

A query can contain a more detailed configuration object:

~~~json
{
  "range": {
    "price": {
      "gte": 500000,
      "lte": 2000000
    }
  }
}
~~~

In this example, `gte` is greater than or equal to and `lte` is less than or equal to. A document matches when its price is between 500,000 and 2,000,000.

A query can also combine multiple sub-queries using `bool`:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "wireless headphones"
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "range": {
          "price": {
            "lte": 2000000
          }
        }
      }
    ]
  }
}
~~~

This is the JSON structure typically passed to the `StringQuery` constructor.

## 4. Preparing the Entity and Executing StringQuery

Suppose the application has a product entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters, and setters
}
~~~

Use `ElasticsearchOperations` to execute it:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> searchWirelessHeadphones() {
        Query query = new StringQuery("""
            {
              "match": {
                "name": {
                  "query": "wireless headphones"
                }
              }
            }
            """);

        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

The example above uses a fixed keyword to focus on illustrating how execution works. In a real application, build the JSON string from dynamic search input safely as shown in the dynamic query building section below.

The `operations.search(...)` call takes three arguments:

1. The `Query` object, here `StringQuery`.
2. The entity type to which the results will be mapped, here `Product.class`.
3. `IndexCoordinates` specifying the index or alias to search.

The result is `SearchHits<Product>`, which provides the list of documents along with metadata such as ID, score, sort values, and highlight fields.

## 5. Match Query: Full-Text Search

`match` is a query commonly used for `text` fields. Elasticsearch analyzes the search string with the field's search analyzer and then matches the indexed tokens.

Example:

~~~json
{
  "match": {
    "name": {
      "query": "wireless headphones"
    }
  }
}
~~~

You can adjust how matching works:

~~~json
{
  "match": {
    "name": {
      "query": "wireless headphones",
      "operator": "and",
      "minimum_should_match": "75%"
    }
  }
}
~~~

- `operator: "and"` requires the query tokens to appear together according to match query semantics.
- `operator: "or"` is the common default behavior, allowing any one of the tokens to match.
- `minimum_should_match` adjusts the percentage or number of tokens that must match.

`match` is suitable for natural text search. Do not use it in place of `term` when an exact match on a keyword field is needed.

## 6. Term and Terms Queries: Exact Matching

`term` searches for an indexed value. It is usually suited for `keyword` fields, codes, statuses, and classification values.

~~~json
{
  "term": {
    "category": "audio"
  }
}
~~~

`terms` takes a list of values and matches documents that contain at least one matching value:

~~~json
{
  "terms": {
    "category": [
      "audio",
      "video",
      "accessories"
    ]
  }
}
~~~

This example finds products belonging to one of the three categories.

For `text` fields, the analyzer may transform content at index time. Therefore, `term` with the original string may not match as expected. Check the mapping and Analyze API output before choosing an operator.

## 7. Range Query: Searching by Value Range

`range` supports greater-than, less-than, and two-sided bounds:

~~~json
{
  "range": {
    "price": {
      "gte": 500000,
      "lt": 2000000
    }
  }
}
~~~

Common operators:

| Operator | Meaning |
|---|---|
| `gt` | Greater than |
| `gte` | Greater than or equal to |
| `lt` | Less than |
| `lte` | Less than or equal to |

For date fields, a range query can use date values and relative date expressions supported by Elasticsearch:

~~~json
{
  "range": {
    "createdAt": {
      "gte": "now-30d/d",
      "lt": "now"
    }
  }
}
~~~

The example searches for documents created within the last 30 days, calculated using the day rounding specified by the `/d` expression.

Range queries require fields with an appropriate data type. Prices should be numeric fields and dates should be `date`; do not use plain keyword strings if numeric or time-based comparisons are needed.

## 8. Bool Query: Combining Multiple Conditions

`bool` is a core building block for constructing compound queries. It has four main clause groups:

| Clause | Role | Impact on score |
|---|---|---|
| `must` | Mandatory condition that must match | Can contribute to the score |
| `filter` | Mandatory condition that must match | Does not calculate a score |
| `should` | Preferred condition or conditional match depending on configuration | Can contribute to the score |
| `must_not` | Condition that must not match | Does not calculate a score |

Example finding products whose name relates to `wireless`, belonging to category `audio`, priced at most 2,000,000, and currently active:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "wireless"
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "range": {
          "price": {
            "lte": 2000000
          }
        }
      },
      {
        "term": {
          "active": true
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "status": "DISCONTINUED"
        }
      }
    ]
  }
}
~~~

In the example:

- `must` defines the main search content and can affect relevance.
- `filter` restricts the category, price, and active status.
- `must_not` excludes discontinued products.

### Should and minimum_should_match

`should` can be used to boost certain results:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "headphones"
        }
      }
    ],
    "should": [
      {
        "term": {
          "brand": "Acme"
        }
      },
      {
        "term": {
          "featured": true
        }
      }
    ],
    "minimum_should_match": 0
  }
}
~~~

Here, products with brand `Acme` or marked as featured can receive a higher score. `minimum_should_match: 0` allows documents that do not match the should branches to still be returned if they satisfy must.

If at least one should branch is required to match, set `minimum_should_match: 1`. Note that the default value of `minimum_should_match` varies depending on whether the bool query has must/filter clauses; declare it explicitly when business logic requires a specific number of branches.

## 9. Multi-Match Query: Searching Across Multiple Fields

When a user enters a phrase and you want to search across multiple text attributes, `multi_match` can be used:

~~~json
{
  "multi_match": {
    "query": "wireless noise cancelling",
    "fields": [
      "name^3",
      "description",
      "brandName^2"
    ],
    "type": "best_fields"
  }
}
~~~

Where:

- `query` is the search string.
- `fields` is the list of fields to search.
- `^3` and `^2` are boosts that increase the priority of the corresponding fields.
- `best_fields` is one of the multi-match types, suitable when a single well-matching field can determine relevance.

`multi_match` can be combined with a bool filter:

~~~json
{
  "bool": {
    "must": [
      {
        "multi_match": {
          "query": "wireless noise cancelling",
          "fields": [
            "name^3",
            "description"
          ]
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      }
    ]
  }
}
~~~

Boost helps adjust the result ordering, not enforce a mandatory condition. If you need to control relevance, test with a representative query suite and evaluate actual results.

## 10. Nested Query: Searching Inside Nested Objects

When a field is mapped as `nested`, the query must declare `nested` and `path` to scope the child object.

For example, a product document with variants:

~~~json
{
  "variants": [
    {
      "color": "black",
      "size": "S",
      "stock": 0
    },
    {
      "color": "white",
      "size": "M",
      "stock": 12
    }
  ]
}
~~~

The `variants` mapping must be `nested`. A query to find a variant that is both black and in stock:

~~~json
{
  "nested": {
    "path": "variants",
    "query": {
      "bool": {
        "filter": [
          {
            "term": {
              "variants.color": "black"
            }
          },
          {
            "range": {
              "variants.stock": {
                "gt": 0
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Both conditions reside inside the same nested query, so they must match on the same nested object. The example document does not match because the black variant has stock equal to 0.

If the field is only mapped as `object`, Elasticsearch flattens the properties of the object array and conditions across two different objects can accidentally combine. Use a nested query when business logic requires preserving correlation between properties of the same element.

## 11. Creating StringQuery for Real-World Search Conditions

Once you understand the query clauses, you can assemble them into a JSON Query DSL and pass it to `StringQuery`.

Example searching products by name, category, and maximum price:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

Query query = new StringQuery("""
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wireless headphones",
            "operator": "and"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "range": {
          "price": {
            "lte": 2000000
          }
        }
      }
    ]
  }
}
""");
~~~

Pagination can be attached through the constructor:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery(
    """
    {
      "bool": {
        "filter": [
          {
            "term": {
              "category": "audio"
            }
          }
        ]
      }
    }
    """,
    PageRequest.of(0, 20),
    Sort.by(Sort.Direction.ASC, "price")
);
~~~

`StringQuery` provides constructors accepting `source`, `source` with `Pageable`, or `source` with `Pageable` and `Sort`. These options belong to Spring Data Query, so there is no need to embed `from`, `size`, or `sort` inside the query clause string.

## 12. Building Dynamic JSON Safely

In real applications, search values usually come from user requests. Do not concatenate input data directly into a JSON string:

~~~java
// Avoid doing this
String source = """
{
  "match": {
    "name": "%s"
  }
}
""".formatted(keyword);
~~~

If `keyword` contains quotes, slashes, or specially structured content, the JSON may become invalid or be altered unintentionally. String concatenation also makes escaping hard to control in code.

A safer approach is to build a Java structure and use a JSON serializer to convert it into a string. For example, with Jackson `ObjectMapper`:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

public Query buildProductQuery(
        ObjectMapper objectMapper,
        String keyword,
        String category,
        Double maxPrice) throws JsonProcessingException {

    Map<String, Object> match = Map.of(
        "match",
        Map.of(
            "name",
            Map.of("query", keyword)
        )
    );

    List<Map<String, Object>> filters = List.of(
        Map.of("term", Map.of("category", category)),
        Map.of("range", Map.of("price", Map.of("lte", maxPrice)))
    );

    Map<String, Object> queryDsl = Map.of(
        "bool",
        Map.of(
            "must", List.of(match),
            "filter", filters
        )
    );

    String json = objectMapper.writeValueAsString(queryDsl);
    return new StringQuery(json);
}
~~~

Jackson is responsible for escaping strings and producing valid JSON. The application must still validate input data—for example, ensuring `keyword` is non-empty, `category` belongs to an allowed list, and `maxPrice` is non-negative if business rules require it.

If a condition is optional, add the clause only when a value is present. Do not arbitrarily insert `null` into the query DSL. You can build the `must` and `filter` lists using mutable collections and then serialize them to JSON.

For complex dynamic queries, `CriteriaQuery` or `NativeQuery` may be easier to maintain than constructing many Maps manually. `StringQuery` is best suited when the JSON structure is relatively stable and you want to preserve the Query DSL representation.

## 13. Distinguishing StringQuery from @Query on Repositories

The two mechanisms have similar names but are used differently:

- `StringQuery` is a class in the `org.springframework.data.elasticsearch.core.query` package, instantiated in Java code and passed to `ElasticsearchOperations`.
- `@Query` is an annotation on a repository method that allows declaring a JSON query directly on the interface.

`StringQuery` example:

~~~java
Query query = new StringQuery("""
{
  "match": {
    "name": {
      "query": "wireless"
    }
  }
}
""");

SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

Repository `@Query` example with a placeholder:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"match\":{\"name\":{\"query\":\"?0\"}}}")
    List<Product> searchByName(String keyword);
}
~~~

In repository queries, `?0` represents the first method parameter, `?1` the second, and so on in order. Placeholders are processed by the repository query method mechanism.

Do not assume `StringQuery` automatically replaces `?0` with Java arguments. With `StringQuery`, generate JSON whose values are already safely serialized, or choose a query-building API with explicit parameterization.

## 14. Combining Query Options Outside JSON

The string passed to `StringQuery` describes the query clause. Other execution options can be set on the query object after creation.

Example with pagination, sorting, and limiting total hits:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery("""
{
  "match": {
    "name": {
      "query": "wireless"
    }
  }
}
""");

query.setPageable(PageRequest.of(
    0,
    25,
    Sort.by(Sort.Direction.DESC, "price")
));

query.setTrackTotalHits(false);
~~~

Some options commonly managed outside the JSON query clause:

- `Pageable`: page number and page size.
- `Sort`: sort order.
- `SourceFilter`: fields to include or exclude from `_source`.
- `trackTotalHits` or `trackTotalHitsUpTo`: how total hits are tracked.
- `minScore`: minimum score threshold.
- `timeout`: search time limit.
- `preference` and `routing`: shard selection or request routing.
- `searchAfter`: continuing pagination based on sort values.

Specific methods may vary depending on the Spring Data Elasticsearch version. Check the API of the dependency your project uses before copying configuration.

## 15. Reading SearchHits Results

When executed:

~~~java
SearchHits<Product> hits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

`SearchHits<Product>` contains search metadata along with the hits. You can iterate over the results:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    String id = hit.getId();
    float score = hit.getScore();

    // Process product, id, and score
}
~~~

In addition to the entity, each hit can provide:

- Document ID.
- Score representing relevance.
- Sort values used for `search_after`.
- Highlight fields if the query requested highlighting.
- Inner hits in certain nested queries.

If you only convert results to `List<Product>`, the application loses convenient access to per-hit metadata. For search screens that need to display scores, highlight snippets, or deep pagination, keep `SearchHits` or `SearchHit`.

## 16. Checking Query DSL Before Deployment

A JSON string can be syntactically valid yet semantically wrong. It should be checked across multiple layers:

**Verify JSON.** Ensure brackets, quotes, commas, and data types are valid. If JSON is built dynamically, use a serializer instead of manual escaping.

**Verify mapping.** Confirm the field exists and has an appropriate type. `term` on keyword, `match` on text, and `range` on numeric/date are common choices.

**Verify analyzer.** For `match` or `multi_match`, use the Analyze API to confirm that query text is tokenized as expected.

**Test directly via REST API.** Run the query clause inside the body of `/_search` to observe results before putting it into Java code. When moving to `StringQuery`, extract only the object inside `query`.

**Run integration tests.** Use an Elasticsearch version compatible with your application's Spring Data version. Create sample data, execute `StringQuery`, and verify returned documents, scores, sorting, and pagination.

**Monitor performance.** Wildcard, regexp, nested, or multi-branch bool queries can be resource-intensive. Evaluate them on production-like data and cap page sizes.

## 17. Common Mistakes

**Passing the entire search request body into StringQuery.** `StringQuery` expects a query clause, such as `{"match": ...}`. Do not wrap it in `{"query": ...}` like a REST `_search` body.

**Confusing term with match.** `term` does not analyze the search string like `match` does. Use `term` for exact values, typically keyword fields; use `match` for full-text fields.

**Using the wrong field type in range.** Range on keyword strings uses lexicographical semantics, not numeric or temporal semantics. Prices need numeric mapping, and dates need date mapping.

**Putting sort, from, or size inside the query clause.** These belong to search request options. Configure them via `Pageable`, `Sort`, or properties on `Query`.

**Concatenating input directly into JSON.** Data containing quotes or special characters can break JSON. Use Jackson or a safe query builder.

**Assuming StringQuery supports `?0` placeholders.** Placeholders are a mechanism of repository `@Query`; `StringQuery` does not automatically bind parameters that way.

**Forgetting nested mapping.** Queries with `nested` only work properly when the field is declared as `nested` in the mapping and `path` points to that field.

**Skipping pagination.** Queries can return more results than the UI needs. Set `Pageable`, cap the page size, or use `search_after` for deep pagination.

**Checking only JSON syntax without checking results.** Valid JSON does not guarantee the query matches business logic. Test on sample data and verify the semantics of mappings, analyzers, and bool clauses.

## 18. Workflow for Using StringQuery in a Project

You can follow this sequence:

1. Identify the search requirements and relevant fields.
2. Check the mapping to see whether each field is `text`, `keyword`, numeric, date, or nested.
3. Write a minimal Query DSL via the REST API and verify the results.
4. Extract only the query clause portion for `StringQuery`.
5. If the query has dynamic parameters, construct a Java structure and serialize it to JSON.
6. Create `StringQuery` from the finalized JSON string.
7. Configure `Pageable`, `Sort`, source filtering, and execution options on `Query`.
8. Call `ElasticsearchOperations.search(...)` with the entity type and index coordinates.
9. Retain `SearchHits` when scores, sort values, highlights, or metadata are needed.
10. Verify with integration tests and monitor performance on realistic data.

## Conclusion

`StringQuery` is a way to represent Spring Data Elasticsearch queries as JSON Query DSL strings. It is useful when you already have JSON queries or need direct control over clauses such as `match`, `term`, `range`, `bool`, `multi_match`, and `nested`.

The input string is the query clause, while pagination, sorting, source filtering, and other execution options are configured on the `Query` object. For dynamic data, build a Java structure and serialize it with a JSON mapper to avoid escaping bugs and injection. When stronger type checking or complex dynamic query construction is needed, consider `CriteriaQuery` or `NativeQuery`.

## References

- [Spring Data Elasticsearch — Elasticsearch Operations and Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — StringQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/StringQuery.html)
- [Elasticsearch — Query DSL](https://www.elastic.co/docs/reference/query-languages/query-dsl)
- [Elasticsearch — Bool query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query)
- [Elasticsearch — Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
