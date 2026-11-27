# Exists Query and the Meaning of Missing Values

In Elasticsearch, a field can appear in a JSON document without having any indexed value available for search. Conversely, a field can have an indexed value even when the application does not need to inspect its specific content. Therefore, when you need to find documents that have or lack data in a field, you must understand how **an existing value in the index** differs from **a property appearing in `_source`**.

Elasticsearch provides the **exists query** to find documents that have an indexed value for a field. To find documents missing a value, you typically place an exists query inside a bool query's `must_not` clause.

In Spring Data Elasticsearch, this query can be constructed with Elasticsearch Java API Client `Query`, wrapped in `NativeQuery`, and executed through `ElasticsearchOperations`. Understanding exact exists semantics prevents confusion among null, empty string, empty array, and unindexed fields.

## 1. What Does the Exists Query Check?

An exists query returns documents where the field has at least one indexed value in Elasticsearch. It does not simply check whether the property name appears in the original JSON.

Suppose the `products` index contains documents:

~~~json
{ "name": "Mechanical Keyboard", "description": "A keyboard for work" }
{ "name": "Wireless Mouse" }
{ "name": "USB Hub", "description": null }
{ "name": "Monitor Stand", "description": "" }
~~~

With the query:

~~~json
{
  "query": {
    "exists": {
      "field": "description"
    }
  }
}
~~~

Documents having an indexed `description` value are returned. In the example above:

- The document with `"A keyboard for work"` has an existing field value.
- The document omitting `description` has no value to index.
- The document with `description: null` is treated by default as having no indexed value.
- The document with `description: ""` still has an empty string value; an empty string counts as existing.

Results depend on the mapping and how data is indexed. A value present in `_source` may still not count as existing if Elasticsearch did not index that value.

## 2. How Do Missing Fields, null, and Empty Strings Differ?

These are three cases to distinguish when designing filters.

| Data in document | Default exists result | Explanation |
|---|---|---|
| Field omitted | Does not match | No indexed value |
| `"description": null` | Does not match | JSON null is not indexed by default |
| `"description": ""` | Matches | An empty string is still a value |
| `"description": " "` | Matches | A whitespace-only string is still a value |
| `"description": []` | Does not match | An empty array has no elements to index |
| `"description": ["A", "B"]` | Matches | At least one element is indexed |
| `"description": [null, "A"]` | Matches | Element "A" is indexed |

For arrays, an exists query only needs one element with an indexed value for the document to match. An array containing null alongside a valid value still counts as existing.

Do not use exists to check whether a string contains meaningful text. If your application considers empty or whitespace-only strings to be missing, normalize data before indexing or add appropriate business conditions.

### JSON null is not SQL NULL

Elasticsearch is not a relational database, and an exists query is not a direct SQL `IS NULL` check. Elasticsearch searches for values present in its indexed structures.

By default, JSON `null` and an omitted field both produce no searchable term for that field. If your business logic must distinguish those two cases, store an explicit status field or use an agreed sentinel value.

## 3. Mapping and Data Example

A product entity can be declared as:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

In the mapping:

- `sku` is keyword, commonly used for exact matching.
- `description` is text, used for full-text search.
- `status` is keyword, fitting statuses such as `PUBLISHED` or `DRAFT`.

An exists query can check any indexed field, whether the field is text, keyword, numeric, date, or another indexable type.

Example document:

~~~json
{
  "sku": "KB-1001",
  "description": "Mechanical keyboard for office use",
  "status": "PUBLISHED"
}
~~~

An exists query on `description` does not search for "keyboard". It only checks whether the document has an indexed value for that field.

## 4. Finding Documents Having a Field with Exists Query

Basic Query DSL:

~~~json
{
  "query": {
    "exists": {
      "field": "description"
    }
  }
}
~~~

Multiple conditions can be combined in a bool query. For example, finding published products that have a description:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        },
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

`filter` is appropriate because field existence only narrows the result set and needs no relevance scoring.

When combining with full-text search, put `match` inside `must` and exists inside `filter`:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

This query both searches the name by content and requires the document to have an indexed value for `description`.

## 5. Finding Documents Missing a Field with must_not exists

To find documents that do not have an indexed value for a field, place an exists query inside `must_not` of a bool query:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

Results include documents that:

- Omit the `description` property.
- Have `description: null` under default mapping.
- Have an empty array `description: []`.
- Have a value that was not indexed due to a mapping option or a configured ignored data error.

Example finding published products that do not yet have a description:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        }
      ],
      "must_not": [
        {
          "exists": {
            "field": "description"
          }
        }
      ]
    }
  }
}
~~~

`must_not` is an exclusion condition. The query does not search for a specific null literal; it excludes documents that have an indexed value for the field.

### Distinguishing must_not exists from term null

Do not write:

~~~json
{
  "query": {
    "term": {
      "description": null
    }
  }
}
~~~

This is not the standard way to search for missing fields or JSON null. Use `must_not exists` when looking for documents without an indexed value.

## 6. Reasons a Value in `_source` May Not Count as Existing

Certain mapping configurations can cause a value to remain in `_source` while having no indexed value for the field.

| Cause | Example | Impact on exists |
|---|---|---|
| Field omitted | Field does not appear in JSON | Does not match |
| Default null value | `"description": null` | Does not match |
| Empty array | `"tags": []` | Does not match |
| Exceeds `ignore_above` | Keyword string longer than limit | That field has no indexed value |
| Malformed format with `ignore_malformed` enabled | Invalid string for numeric/date | Field value skipped during indexing |
| Both `index` and `doc_values` disabled | Field lacks lookup structures | Cannot be checked with exists |
| Dynamic mapping skips indexing field | New field inside `dynamic: false` object | Value may stay in source without being mapped/indexed |

### ignore_above

For keyword fields, a length limit can be configured:

~~~json
{
  "mappings": {
    "properties": {
      "externalCode": {
        "type": "keyword",
        "ignore_above": 20
      }
    }
  }
}
~~~

If a document contains an `externalCode` longer than 20 characters, the value can still be stored in `_source`, yet not indexed for the `externalCode` field. An exists query on this field will not match that document.

If using a multi-field, such as `name` as text and `name.keyword` as keyword with `ignore_above`, exists results across the two fields can differ. The main text field may exist while the keyword subfield has no indexed value.

### ignore_malformed

For numeric or date fields, `ignore_malformed` lets Elasticsearch skip malformed values rather than rejecting the whole document.

~~~json
{
  "mappings": {
    "properties": {
      "rating": {
        "type": "integer",
        "ignore_malformed": true
      }
    }
  }
}
~~~

If a document has `"rating": "not-a-number"`, the rating value may be skipped at index time. The document can still be indexed with its other valid fields; an exists query on `rating` does not match that document.

Do not enable `ignore_malformed` just to hide bad data. If business rules require rating to always be a valid number, validate in the application and monitor data errors.

### index and doc_values

An exists query needs searchable/lookup data in an appropriate index structure. If a field is configured with both indexing and doc values disabled, Elasticsearch has no structure to check existence via query.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "internalNote": {
        "type": "keyword",
        "index": false,
        "doc_values": false
      }
    }
  }
}
~~~

`internalNote` can still reside in `_source`, yet an exists query cannot find documents based on this field. For keyword fields, disabling only `index` while keeping `doc_values` enabled may still allow existence checks/reads via doc values; inspect the full mapping rather than looking at a single property alone.

### Dynamic mapping

If an object has `dynamic: false`, new fields can remain in source without being added to the mapping. In that case, an exists query on an unindexed field cannot find that value.

This is why you should check the actual mapping whenever exists query results differ from the JSON content the application sent.

## 7. `null_value`: Turning null into a Searchable Value

Elasticsearch supports the `null_value` mapping parameter on certain field types. When a document has a JSON null value, Elasticsearch substitutes a sentinel value during indexing.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "status": {
        "type": "keyword",
        "null_value": "UNKNOWN"
      }
    }
  }
}
~~~

With this mapping, the document:

~~~json
{
  "status": null
}
~~~

is indexed for field `status` using sentinel value `UNKNOWN`. As a result:

- An exists query on `status` will match.
- A term query with `status = UNKNOWN` can match.
- The value in `_source` remains JSON null; `null_value` does not modify source content.

Query example:

~~~json
{
  "query": {
    "term": {
      "status": "UNKNOWN"
    }
  }
}
~~~

Use `null_value` when business logic wants to represent null as a searchable state. Pick a sentinel that cannot be confused with real values; if a document legitimately has status `UNKNOWN`, queries cannot tell it apart from a substituted null.

`null_value` does not turn a completely omitted field into a valued field. It applies to explicit null values in indexed data, depending on field type and mapping support.

## 8. Exists Queries with Arrays and Objects

### Multi-valued arrays

A field can hold multiple values of the same type:

~~~json
{
  "tags": ["mechanical", "wireless", "office"]
}
~~~

An exists query on `tags` matches if at least one element is indexed. If the array is `[]` or contains only nulls under default mapping, the query does not match.

With an array such as:

~~~json
{
  "tags": [null, "wireless"]
}
~~~

The document still matches because element `wireless` is indexed.

### Regular objects

With object mappings:

~~~json
{
  "manufacturer": {
    "name": "Acme",
    "country": "VN"
  }
}
~~~

Check leaf fields such as `manufacturer.name` or `manufacturer.country`, because those are the fields with concrete mappings and values.

Do not infer that just because the `manufacturer` object appears in source, all child fields exist. An object may contain only a subset of properties.

### Nested fields

With `nested` mappings, child objects are indexed as separate nested documents. When querying fields inside a nested path, wrap the exists query inside a nested query:

~~~json
{
  "query": {
    "nested": {
      "path": "comments",
      "query": {
        "exists": {
          "field": "comments.author"
        }
      }
    }
  }
}
~~~

The query above finds parent documents that have at least one nested comment containing an indexed value for `comments.author`.

To find parent documents that have a nested child missing an author, use a nested query with bool `must_not exists` inside the nested path. That result means at least one nested child lacks an author; it does not mean the parent has zero nested children. Clarify the exact business scope before writing the query.

## 9. Using Exists Query with the Elasticsearch Java API Client

In Spring Data Elasticsearch 5.x, queries can be built using `co.elastic.clients.elasticsearch._types.query_dsl.Query`.

### Finding documents with a field

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query existsQuery = Query.of(q -> q
        .exists(e -> e
                .field("description")
        )
);
~~~

### Finding documents missing a field

~~~java
Query missingDescriptionQuery = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e
                                .field("description")
                        )
                )
        )
);
~~~

In the second example:

- `bool` creates a condition group.
- `mustNot` excludes documents with an indexed value for description.
- `exists` checks the description field.

This is the Elasticsearch Java API Client query DSL, not Spring Data's `org.springframework.data.elasticsearch.core.query.Query` interface. Clear variable names like `missingDescriptionQuery` help avoid confusing the two identically named types.

## 10. Wrapping in NativeQuery and Executing with Spring Data

After creating the Java Client Query, use `NativeQuery` to adapt it into the Spring Data Query abstraction:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

Query missingDescriptionQuery = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e.field("description"))
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(missingDescriptionQuery)
        .build();

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

`ElasticsearchOperations.search(...)` executes the query and maps results to `ProductDocument`. `SearchHits` contains metadata and matched hits.

Example service finding products without descriptions:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductAuditService {

    private final ElasticsearchOperations operations;

    public ProductAuditService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> findWithoutDescription() {
        Query query = Query.of(q -> q
                .bool(b -> b
                        .mustNot(mn -> mn
                                .exists(e -> e.field("description"))
                        )
                )
        );

        NativeQuery nativeQuery = NativeQuery.builder()
                .withQuery(query)
                .build();

        return operations.search(
                nativeQuery,
                ProductDocument.class
        );
    }
}
~~~

If you only need to check a specific value, use a repository finder or term query. Exists queries answer whether a field has an indexed value; they do not replace content queries.

## 11. Combining exists with Other Conditions

### Published products missing an image

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        }
      ],
      "must_not": [
        {
          "exists": {
            "field": "imageUrl"
          }
        }
      ]
    }
  }
}
~~~

### Products with a description and belonging to a category

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "description"
          }
        },
        {
          "term": {
            "category": "ACCESSORIES"
          }
        }
      ]
    }
  }
}
~~~

### Products missing a release date or missing a description

To find documents missing at least one of two fields, use an OR group of missing conditions:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "bool": {
            "must_not": [
              {
                "exists": {
                  "field": "releaseDate"
                }
              }
            ]
          }
        },
        {
          "bool": {
            "must_not": [
              {
                "exists": {
                  "field": "description"
                }
              }
            ]
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

If business logic requires missing both fields, place both missing groups inside `filter` or `must` instead of `should`. Always distinguish "missing at least one" from "missing all".

## 12. How Exists Query Differs from Sort `missing` and Aggregation `missing`

An exists query filters documents based on whether a field has an indexed value. Sort and aggregation offer their own options for handling documents lacking a field; those options do not filter documents.

### Sort with missing

Example sorting by price, placing documents missing price at the end:

~~~json
{
  "sort": [
    {
      "price": {
        "order": "asc",
        "missing": "_last"
      }
    }
  ]
}
~~~

`missing: "_last"` only specifies the position of documents missing price in sorted output. Those documents can still appear in results unless the query excludes them.

To return only documents that have a price, add an exists filter:

~~~json
{
  "query": {
    "exists": {
      "field": "price"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ]
}
~~~

### Aggregation with a missing bucket

A terms aggregation can group documents without a field value into a `missing` bucket if configured:

~~~json
{
  "aggs": {
    "products_by_status": {
      "terms": {
        "field": "status",
        "missing": "UNKNOWN"
      }
    }
  }
}
~~~

The `missing` value in an aggregation is a placeholder for bucketing aggregation output. It does not write back to documents and does not make the field exist in the mapping.

## 13. Distinguishing exists, term, and match

| Query | Question answered | Example |
|---|---|---|
| `exists` | Does the field have an indexed value? | Is there a description? |
| `term` | Does the field have a term matching a specific value? | Is status strictly PUBLISHED? |
| `match` | Does content match search text after analysis? | Does name relate to wireless keyboard? |
| `must_not exists` | Does the field lack an indexed value? | Product has no description yet? |

For example, a document has:

~~~json
{
  "description": "Wireless keyboard for office"
}
~~~

- Exists query on `description` matches.
- Term query with the whole sentence may not match as expected if the field is analyzed text.
- Match query with `keyboard` can match via full-text search.

Exists queries do not inspect content quality, length, or specific values. They only check whether an indexed value for the field can be found.

## 14. Common Mistakes

### Thinking exists checks properties in `_source`

A field can remain in source without having an indexed value due to `ignore_above`, `ignore_malformed`, `dynamic: false`, or a mapping disabling both index and doc values. Inspect actual mappings and data.

### Treating empty strings as missing

An empty string `""` is still considered a value. If business logic treats empty strings as missing, normalize before indexing or add appropriate supplementary conditions.

### Using term null to find missing fields

Term queries are not the way to find missing fields. Use bool `must_not exists`.

### Confusing `null_value` with mutating `_source`

`null_value` only substitutes null during indexing. Source still keeps null, while exists queries can match because the sentinel is indexed.

### Overlooking empty arrays

`[]` has no elements, so it produces no value for exists queries to find. An array with at least one valid element matches.

### Forgetting `ignore_above` on multi-fields

`name` and `name.keyword` can yield different exists results. Check the exact field path the query targets.

### Misusing exists with nested mappings

Nested fields must be queried inside the right nested path. Without a nested query, results may not reflect child object structure as intended.

### Using exists to validate content

Exists does not verify valid email syntax, non-empty descriptions, or numbers within business bounds. Those rules require separate validation.

## 15. Design Workflow for Filtering by Missing Values

When building features to find documents having or missing fields:

1. Clarify whether the business question is "field has an indexed value" or "property appears in source".
2. Inspect the field mapping: type, `null_value`, `ignore_above`, `ignore_malformed`, `index`, `doc_values`.
3. Test sample data including omitted fields, null, empty strings, empty arrays, and valid values.
4. Use `exists` for documents with indexed values.
5. Use `bool.must_not.exists` for documents lacking indexed values.
6. For nested fields, wrap exists inside a nested query with the right path.
7. Combine filters with tenant, status, or access permissions from verified sources.
8. If explicit null must be distinguished from omitted fields, design a sentinel or dedicated status field.
9. Verify queries against real data and actual mappings.
10. Keep missing-value filters distinct from sort/aggregation missing options.

## Conclusion

An exists query finds documents with an indexed value for a field; a bool query with `must_not exists` finds documents without an indexed value. Omitted fields, default JSON nulls, and empty arrays are generally treated as missing, whereas empty strings still count as existing. Mapping options such as `null_value`, `ignore_above`, `ignore_malformed`, `index`, and `doc_values` can alter results. In Spring Data Elasticsearch, exists queries can be constructed with Java Client DSL, wrapped in `NativeQuery`, and executed via `ElasticsearchOperations`.
