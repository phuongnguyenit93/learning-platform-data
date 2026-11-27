# Designing Multi-Fields for Search, Sorting, and Aggregations

A single text property in Elasticsearch often needs to serve multiple usage patterns. Users want to search products by keyword, yet the application also needs to sort product names alphabetically and aggregate product counts by exact name or label. A single field type can rarely satisfy all three needs well.

Elasticsearch solves this with **multi-fields**: the same value is indexed in multiple different ways. The primary field can be `text` for content analysis and full-text search; a `keyword` subfield keeps the value as an intact string for exact matching, sorting, or aggregations.

Spring Data Elasticsearch supports declaring this structure directly on entities via `@MultiField` and `@InnerField`. Proper multi-field design keeps queries clean, avoids enabling memory-heavy `fielddata` on `text`, and establishes a solid foundation for analytics.

## 1. Why does a text field need multiple indexing representations?

Suppose an application manages products and has a `title` property:

~~~text
Wireless Mechanical Keyboard
~~~

For search, a user might enter `mechanical keyboard`. Elasticsearch needs to analyze the string into tokens to find documents containing matching words. This is the job of a `text` field.

However, when sorting a list by name, the application usually wants to compare the title value as a complete string. If using a `text` field, data has already been analyzed into tokens; this field is not optimized for sorting and aggregations. Elasticsearch disables `fielddata` on `text` by default to avoid loading all terms into the JVM heap.

Similarly, when counting products by title or filtering on an exact string code, you need a representation that has not been tokenized. This is the role of `keyword`.

A single field can therefore require different behaviors:

| Requirement | Appropriate handling |
|---|---|
| Searching part of content or words in a sentence | `text` and full-text queries such as `match` |
| Exact matching of a string | `keyword` and `term` |
| String sorting | `keyword` |
| Terms aggregation, grouping counts by value | `keyword` |
| Normalizing strings before comparison | `keyword` with a normalizer if needed |

Multi-fields allow Elasticsearch to store multiple indexed representations derived from the same source value. Consequently, the application can target the right representation for each operation.

## 2. How do multi-fields work?

A multi-field mapping has a main field `title` of type `text` and a `keyword` subfield of type `keyword`:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

When indexing a document:

~~~json
{
  "title": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch indexes the `title` value under both configurations:

- `title` is processed by the analyzer into tokens to serve full-text search.
- `title.keyword` preserves the whole string as a keyword value for exact matching, sorting, and aggregations.

The path `title.keyword` is the field name used in Query DSL. Inside `_source`, the document still contains only the `title` property; the subfield does not create an extra JSON property.

### Processing diagram

~~~text
_source.title = "Wireless Mechanical Keyboard"
                    |
                    v
               Multi-field
                /       \
               /         \
              v           v
        title (text)   title.keyword (keyword)
              |           |
          Analyzer      Whole value
              |           |
        token index    keyword index
              |           |
        match query    term / sort / aggregation
~~~

The two fields are indexed independently while drawing their value from one source property. This does not mean Elasticsearch stores two copies of the string in `_source`; it builds the index structures suited to each field type.

### Multi-fields are not nested objects

`title.keyword` looks like an object path, yet it is not a child JSON object in `_source`. It is a subfield in the mapping.

Multi-fields also differ from `nested` fields. `nested` is used to index child objects while preserving relationships across their properties; multi-fields are used to index the same value under multiple types.

## 3. Declaring multi-fields in Spring Data Elasticsearch

Spring Data Elasticsearch provides two primary annotations:

- `@MultiField`: marks a property with a main field and one or more subfields.
- `@InnerField`: describes each subfield, including its suffix and field type.

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(
            type = FieldType.Text,
            analyzer = "standard"
        ),
        otherFields = {
            @InnerField(
                suffix = "keyword",
                type = FieldType.Keyword
            )
        }
    )
    private String title;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    // constructors, getters, setters
}
~~~

With the declaration above, Spring Data generates metadata corresponding to the mapping:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "standard",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

The subfield name is determined by `suffix`. With `suffix = "keyword"`, the field path in Elasticsearch is `title.keyword`.

You can declare multiple subfields when there is a real need:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword
        ),
        @InnerField(
            suffix = "english",
            type = FieldType.Text,
            analyzer = "english"
        )
    }
)
private String description;
~~~

In this example:

- `description` uses the `standard` analyzer.
- `description.keyword` serves exact matching, sorting, and aggregations.
- `description.english` uses the English analyzer to search with English language rules.

Create only subfields with a clear use case. Each subfield increases indexing cost, index size, and work performed when writing documents.

### Choosing descriptive suffixes

The suffix becomes part of the public field name in the mapping. Pick names that convey intent:

- `keyword` or `raw`: intact string representation.
- `sort`: representation used for sorting.
- `english`, `ngram`: representation serving a specific analyzer or search strategy.

The suffix name does not alter field semantics. `title.raw` is still just a keyword if the mapping declares `type: keyword`.

Within a project, maintain a consistent convention. If one property uses `title.keyword`, another property should not arbitrarily use `name.raw` for the exact same purpose without good reason.

## 4. Distinguishing `text` and `keyword`

Understanding these two field types is the foundation of multi-field design.

### `text` fields

`text` is designed for full-text search. Its analyzer typically consists of:

1. Character filters processing the input string if configured.
2. Tokenizer splitting the string into tokens.
3. Token filters normalizing, removing, or transforming tokens.

For example, the `standard` analyzer can convert:

~~~text
Wireless Mechanical Keyboard
~~~

into tokens roughly like:

~~~text
wireless
mechanical
keyboard
~~~

A `match` query on `title` also analyzes the query with the appropriate search analyzer, enabling it to find documents by individual words instead of requiring the whole string to match identically.

`text` is suitable for:

- Product names, titles, descriptions.
- Article bodies.
- Place names or information searched by words.
- Text fields requiring relevance scoring.

### `keyword` fields

`keyword` is designed for string values that do not need tokenization. The entire string is one term. For instance, `Wireless Mechanical Keyboard` is treated as a single value.

`keyword` is suitable for:

- Product codes, order codes.
- Statuses, categories, labels.
- Emails or identifiers when exact matching is required.
- Subfields used for sorting or aggregations.

By default, `keyword` enables `doc_values`, an on-disk data structure used efficiently for sorting and aggregations. `text` has `doc_values` absent and `fielddata` disabled by default.

### Do not use `term` instead of `match` arbitrarily

Example full-text query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": {
        "query": "mechanical keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

This query searches across analyzed content in the `title` field.

Example exact match:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "title.keyword": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

This query matches the keyword value. With default keywords, letter case and punctuation affect results because the string is kept verbatim. If case-insensitive matching is needed, design an appropriate normalizer and verify query behavior.

A common mistake is sending `term` with user-entered strings against a `text` field. `term` does not analyze the search string like `match`; if the value does not match an indexed term verbatim, results may be empty.

## 5. Designing multi-fields for search

When users enter keywords, search against the primary `text` field. Multi-fields keep full-text and exact-match behaviors separated.

Example query finding titles containing words related to `wireless keyboard`:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": {
        "query": "wireless keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

`operator: "and"` requires all query tokens to match. If omitted, the default behavior is typically `or`, meaning a document can match any of the tokens. Choose `and` or `or` based on the desired search experience.

If the application wants to prioritize documents matching the full phrase, you can combine multiple queries:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "should": [
        {
          "match_phrase": {
            "title": {
              "query": "wireless keyboard",
              "boost": 3
            }
          }
        },
        {
          "match": {
            "title": {
              "query": "wireless keyboard",
              "operator": "and"
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

`match_phrase` prioritizes tokens appearing in order and close proximity in content. `boost` increases the score for the phrase-matching branch. The `title.keyword` field does not need to participate in this full-text query.

### Using `@Query` in repositories

A repository method can declare a JSON query targeting the main field:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "match": {
            "title": {
              "query": "?0",
              "operator": "and"
            }
          }
        }
        """)
    List<Product> searchTitle(String phrase);
}
~~~

This example uses Java text blocks for readability. If the project targets a Java version without text blocks, JSON can be written as a standard string literal. Verify annotation syntax and parameter binding capabilities for your Spring Data Elasticsearch version.

For complex queries, sorting, or aggregations, you can build a `NativeQuery` and call `ElasticsearchOperations`. The `NativeQuery` builder API varies by release; the rule is to pass the exact Elasticsearch field name such as `title.keyword` for operations needing that subfield.

## 6. Designing multi-fields for sorting

Sorting strings requires a stably comparable value. `keyword` is the standard choice because it has `doc_values`.

Example sorting by title ascending:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "keyboard"
    }
  },
  "sort": [
    {
      "title.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

The query still searches `title`, while sorting uses `title.keyword`. Two purposes use two different field paths while sourcing data from the same underlying property.

To sort descending, use `order: "desc"`.

### Sorting is not the same as searching

Sorting by `title.keyword` does not mean Elasticsearch searches by exact intact strings. `query` and `sort` are two independent parts of the Search API:

- `query` determines which documents match.
- `sort` determines the order of matching documents.

You can combine `match` on a text field with sorting on a keyword field, or filter by category and sort by title keyword.

### Case-insensitive sorting

By default, `keyword` preserves original values, so sorting is affected by uppercase/lowercase differences. If business requirements call for case-insensitive sorting, you can use a keyword subfield with a normalizer.

Example mapping with a custom normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "sort": {
            "type": "keyword",
            "normalizer": "lowercase_normalizer"
          }
        }
      }
    }
  }
}
~~~

Then sort using `title.sort`:

~~~http
POST /products/_search
{
  "sort": [
    {
      "title.sort": {
        "order": "asc"
      }
    }
  ]
}
~~~

The normalizer processes the keyword into a single normalized token. In this example, the `lowercase` filter lowercases the string before indexing. Because normalizers affect how values are indexed, verify the mapping and expected output before applying.

Not every analyzer configuration is valid for sorting. Analyzers can split strings into multiple tokens; normalizers for keywords must produce a single token.

### Sorting on multi-type data

Multi-fields only add another indexing representation of the same value. If the value is the string `"100"`, keyword sorting uses lexicographical order; `"100"` may sort before `"20"`. If numeric sorting is needed, store and sort on a numeric field type.

Similarly, dates should be stored as `date` for chronological comparison. Do not use a keyword subfield to replace numeric or date field types.

## 7. Designing multi-fields for aggregations and analytics

Aggregations allow grouping, counting, and computing statistics over indexed data. For strings, `terms` aggregations normally run on keyword fields.

Example counting products by category:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

If you want to group by exact title, use the subfield:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "products_by_title": {
      "terms": {
        "field": "title.keyword",
        "size": 20
      }
    }
  }
}
~~~

`size: 0` at the search level requests no document hits; the response focuses on aggregations. `terms.size` limits how many buckets are returned. It does not necessarily limit how many distinct values exist across the entire index.

### Why should aggregations use `keyword`?

A `terms` aggregation needs efficient access to field values. Keyword fields have `doc_values` and are designed for this operation. Text fields disable `fielddata` by default because loading terms into heap can consume massive memory.

If you attempt an aggregation on `title` and Elasticsearch returns an error requesting `fielddata`, do not rush to enable `fielddata`. First check whether a keyword subfield exists and use `title.keyword`.

`fielddata: true` on `text` can be useful in specialized cases, yet can dramatically increase heap usage. A keyword multi-field is usually the cleaner and more predictable choice for sorting and aggregations.

### Counting aggregations

A `terms` aggregation can return buckets like:

~~~json
{
  "aggregations": {
    "products_by_title": {
      "buckets": [
        {
          "key": "Wireless Mechanical Keyboard",
          "doc_count": 18
        },
        {
          "key": "Compact Keyboard",
          "doc_count": 11
        }
      ]
    }
  }
}
~~~

`key` is the bucket's keyword value and `doc_count` is the number of documents in that bucket.

If there are very many distinct values, a `terms` aggregation only returns a configured number of buckets and may require adjusting `size`, `shard_size`, or using a `composite` aggregation for pagination. Avoid setting an arbitrarily huge `size`, as bucket counts and merge overhead can spike sharply.

### Cardinality and unique value counts

If you only need an approximate count of distinct values, use a `cardinality` aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "unique_titles": {
      "cardinality": {
        "field": "title.keyword"
      }
    }
  }
}
~~~

Cardinality aggregations typically use an approximation algorithm, so results may not be 100% exact. If business rules require exact unique counts per value, choose an appropriate query or data processing strategy rather than assuming cardinality is an exact count.

## 8. Combining search, sorting, and aggregations in one request

The Search API lets you combine multiple operations in a single request. For example, searching products whose title relates to `keyboard`, sorting by keyword title, and simultaneously aggregating results by category:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": {
        "query": "keyboard",
        "operator": "and"
      }
    }
  },
  "sort": [
    {
      "title.keyword": {
        "order": "asc"
      }
    }
  ],
  "from": 0,
  "size": 20,
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

This request has three parts:

1. `query` finds documents matching analyzed title content.
2. `sort` orders matching results by intact title value.
3. `aggs` aggregates categories within the set of documents matching the query.

The aggregation here is computed over the documents matched by the query, not the entire index. If you need an index-wide aggregation regardless of query, design a `global` aggregation or a separate request as appropriate.

### What role does Spring Data Elasticsearch play?

In a Spring application, entity annotations describe the multi-field mapping. Repositories or `ElasticsearchOperations` construct Search API requests and parse responses.

- `@MultiField` and `@InnerField` describe the mapping structure.
- Repository methods handle common queries.
- `NativeQuery` fits advanced Query DSL, sorting, and aggregations.
- `SearchHits<T>` holds the list of entities along with hit metadata.
- Aggregation results are read from the aggregation portion of the response via the corresponding Spring Data API.

How aggregations are constructed and read in Java changes across versions of Spring Data Elasticsearch and the Elasticsearch Java API Client. When implementing, verify the API of your release train and pass exact Elasticsearch field names like `title.keyword` in requests.

## 9. Creating and updating multi-field mappings

Declaring annotations on an entity does not mean existing indices automatically change their mappings.

When the application creates a new index from entity metadata, Spring Data can generate a mapping containing multi-fields. However, if the index already exists, Elasticsearch does not convert old mappings just because Java code added `@MultiField`.

### Checking the current mapping

Use the Mapping API:

~~~http
GET /products/_mapping
~~~

Check whether the property has the expected structure:

~~~json
{
  "title": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

If `title.keyword` does not exist, queries sorting or aggregating on that subfield will fail.

### Adding a multi-field to an existing mapping

Elasticsearch allows adding a new subfield to an existing field via the Put Mapping API in supported cases:

~~~http
PUT /products/_mapping
{
  "properties": {
    "title": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

The name and type of the main field must match the existing mapping. You cannot arbitrarily change the type of an already indexed field from `text` to `keyword` in place; changing field types usually requires creating a new index and reindexing.

Important point: adding a subfield to a mapping does not automatically reindex existing document values into the new subfield. New or reindexed documents will populate the subfield. Old documents may lack terms/doc values for `title.keyword`, so sorting and aggregations will miss them.

### Reindexing old data

A safe strategy is creating a new index with the complete mapping, then reindexing data:

~~~http
POST /_reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

General workflow:

1. Create the destination index with the new multi-field mapping.
2. Reindex data from the old index to the new index.
3. Verify document count and mapping.
4. Test full-text search, sorting, and aggregations on the new index.
5. Switch the alias or application configuration to the new index according to your deployment plan.
6. Delete the old index only after confirming no callers need it and an adequate backup exists.

For live systems, account for concurrent writes during reindexing, aliases, write aliases, and change-sync strategies. Do not switch traffic before destination data and mappings are ready.

### Mapping templates and new indices

If the system creates time-based indices or uses data streams, update the index template so all new indices receive the multi-field. If you only patch one current index, subsequently rolled-over indices may still lack the new mapping.

Spring Data annotations describe mappings for entities, while managing index templates, aliases, rollovers, and reindexing typically requires dedicated deployment workflows.

## 10. Normalizers for exact match and sorting

Keyword fields preserve intact strings, yet may need normalization for case-insensitive exact matching or character normalization.

Normalizers operate on `keyword` fields and must emit a single token. Example lowercase normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folded_keyword": {
          "type": "custom",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "folded": {
            "type": "keyword",
            "normalizer": "folded_keyword"
          }
        }
      }
    }
  }
}
~~~

The `title.folded` subfield stores the normalized form. You can use it for case-insensitive exact matching and sorting by normalized rules.

Example:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "title.folded": "WIRELESS KEYBOARD"
    }
  },
  "sort": [
    {
      "title.folded": {
        "order": "asc"
      }
    }
  ]
}
~~~

The normalizer processes the query value according to the keyword field's configuration. Test results with a dataset containing uppercase, lowercase, and Vietnamese diacritics if the application supports multiple languages.

When using `asciifolding`, diacritics may be stripped per filter rules. This is a business decision: collapsing accented and unaccented strings is not always desirable.

## 11. Common mistakes when designing multi-fields

### Using a `text` field for sorting or aggregations

`text` is optimized for full-text search. Sorting or aggregating on it typically fails by default because `fielddata` is disabled. Use a `keyword` subfield.

### Using `term` on an analyzed field

`term` does not analyze the search string like `match`. Check the field mapping and query goal before choosing a query type.

### Assuming subfields appear in `_source`

Multi-fields are a way to index one property multiple times. `_source` still contains only the original property. Do not write code expecting a new JSON property named `title.keyword`.

### Adding a multi-field and expecting old data to populate automatically

New mappings do not automatically reindex existing documents. You need to reindex or run an update process so the new subfield has data.

### Creating too many subfields

Each subfield increases indexing and storage overhead. Do not create multiple analyzers or keyword variants unless concrete queries actually need them.

### Using `keyword` for uncontrolled long strings

Keywords have practical limits on term size. For long content, consider `ignore_above`, suitable analyzers, or creating keyword subfields only for appropriately bounded values. `ignore_above` can prevent long values from being indexed into the subfield, causing exact matches, sorting, and aggregations on those values to miss them unexpectedly.

### Using `keyword` to sort numbers or dates

Keywords sort lexicographically. If values represent numbers or dates, use appropriate numeric or date types for proper sorting semantics.

### Enabling `fielddata` to work around an improper mapping

Enabling `fielddata` on `text` can consume large amounts of heap. First design a keyword subfield and verify the mapping; use `fielddata` only when there is a special reason and memory load has been evaluated.

## 12. Inspecting and debugging multi-fields

When search, sorting, or aggregation results are wrong, check in sequence.

### Inspect the mapping

~~~http
GET /products/_mapping
~~~

Confirm:

- The primary field has the right `text` type.
- The analyzer has the right name and configuration.
- Subfields have the right suffixes and `keyword` type.
- Normalizers exist and are bound to the right subfields.
- All indices behind an alias share the same mapping.

If an alias points to multiple indices with differing mappings, a query may behave differently across indices or fail during sorting/aggregations.

### Inspect the analyzer

Use the Analyze API to see how strings are tokenized:

~~~http
POST /products/_analyze
{
  "field": "title",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Output shows tokens, positions, and offsets. If tokens do not match expectations, inspect the analyzer, tokenizer, and token filters.

### Check field capabilities

You can use the Field Capabilities API to inspect field types across one or more indices:

~~~http
GET /products/_field_caps?fields=title,title.keyword
~~~

This is useful when an alias points to multiple indices and you need to confirm `title.keyword` has the same type and is sortable/aggregatable across every index.

### Test each operation separately

Before combining queries, sorting, and aggregations, test each independently:

1. `match` on `title`.
2. `term` on `title.keyword`.
3. `sort` on `title.keyword`.
4. `terms` aggregation on `title.keyword`.

If each part works independently, combining them afterward makes isolating issues easier. Check both old documents and new documents after mapping changes.

### Watch for missing data in subfields

If sorting or aggregations omit certain documents, check:

- Whether the document has a `title` value.
- Whether the subfield already existed when the document was indexed.
- Whether the value exceeded the `ignore_above` limit.
- Whether old documents have been reindexed.
- Whether any document was written to another index under the alias with a different mapping.

Not every hit has a value in every subfield. Define clearly how the application handles missing values when sorting.

## 13. End-to-end design example for `Product`

Suppose an application needs three features:

- Search products by keywords in the title.
- Sort results by title case-insensitively.
- Aggregate product counts by each title.

The mapping can be designed as follows:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword"
          },
          "sort": {
            "type": "keyword",
            "normalizer": "lowercase_normalizer"
          }
        }
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      }
    }
  }
}
~~~

In the Spring Data entity, declare correspondingly:

~~~java
@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "standard"
    ),
    otherFields = {
        @InnerField(
            suffix = "keyword",
            type = FieldType.Keyword
        ),
        @InnerField(
            suffix = "sort",
            type = FieldType.Keyword,
            normalizer = "lowercase_normalizer"
        )
    }
)
private String title;
~~~

The custom normalizer must be declared in index settings before the mapping references it. In Spring Data, settings can be managed via an index configuration file or a dedicated index creation workflow suited to the project. Merely naming the normalizer in an annotation does not create the normalizer definition if settings omit it.

Search:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "wireless keyboard"
    }
  }
}
~~~

Sort:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "keyboard"
    }
  },
  "sort": [
    {
      "title.sort": {
        "order": "asc"
      }
    }
  ]
}
~~~

Aggregate:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "titles": {
      "terms": {
        "field": "title.keyword",
        "size": 50
      }
    }
  }
}
~~~

A single `title` property serves three use cases. `title` handles full-text search, `title.sort` handles case-insensitive ordering, and `title.keyword` groups intact values.

## 14. Design and operational principles

When designing multi-fields for Spring Data Elasticsearch, start from the queries and operations the application actually needs:

- Use `text` for content needing analyzers and full-text search.
- Add a `keyword` subfield when exact matching, sorting, or aggregations are needed.
- Use a normalizer on `keyword` when explicit normalization rules are required.
- Use `numeric`/`date` fields for numbers and timestamps; keywords do not replace their semantics.
- Keep subfield counts minimal to limit indexing and storage overhead.
- Inspect live mappings on the cluster rather than relying solely on Java annotations.
- When adding subfields to an index with existing data, plan reindexing or updating old documents.
- Ensure all indices behind an alias share compatible mappings.
- Use `NativeQuery` or the corresponding Search API when combining advanced queries, sorting, and aggregations.
- Check for missing values and keyword limits if sort/aggregation results are incomplete.

Multi-fields let you represent one property for multiple purposes while keeping the entity model simple. By choosing the right analyzers, keyword subfields, and mapping lifecycle, an application can search flexibly, sort reliably, and aggregate data efficiently on the same document field.
