# Mapping Arrays, Collections, and Multi-Valued Fields

## 1. How Does Elasticsearch Represent Multi-Valued Fields?

In Elasticsearch, a field can hold a single value or multiple values of the same type. Elasticsearch does not have a dedicated mapping type called `array`. Arrays are represented directly in the JSON document, while the mapping describes the data type of each element.

For example, a product has multiple tags and multiple ratings:

~~~json
{
  "name": "Wireless Headphones",
  "tags": ["audio", "bluetooth", "wireless"],
  "ratings": [4, 5, 5, 4]
}
~~~

The mapping can be declared as:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "tags": {
        "type": "keyword"
      },
      "ratings": {
        "type": "integer"
      }
    }
  }
}
~~~

Here:

- `name` is a text value analyzed for full-text search.
- `tags` is a multi-valued keyword field. Each tag is indexed as a separate value of the same field.
- `ratings` is a multi-valued integer field.

The mapping does not need to declare `type: array`. Elasticsearch infers multiple values from the document's JSON structure. Another document can contain a single value for `tags`, such as `"tags": "audio"`, while still using the exact same keyword mapping.

The important requirement is that values of the same field must be compatible with a single mapping type. Do not send one document with `ratings` as an integer array and another document sending a text string into the same field. The field's mapping is shared across the index; an incompatible value can cause indexing to fail.

## 2. Mapping Arrays and Collections from Java

In a Spring Data Elasticsearch application, a Java property can be an array, `List`, `Set`, or another suitable `Collection` type. `MappingElasticsearchConverter` converts those properties into JSON structures when writing documents and converts data from `_source` back to Java objects when reading.

Product entity example:

~~~java
import java.util.List;
import java.util.Set;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Integer)
    private int[] ratings;

    @Field(type = FieldType.Keyword)
    private Set<String> supportedLanguages;

    // Constructors, getters and setters
}
~~~

The corresponding properties can be stored as JSON like this:

~~~json
{
  "id": "p-100",
  "name": "Wireless Headphones",
  "tags": ["audio", "bluetooth", "wireless"],
  "ratings": [4, 5, 5, 4],
  "supportedLanguages": ["en", "vi"]
}
~~~

Key points to understand:

- `List<String>` represents a sequence of values and preserves order in the Java object.
- `Set<String>` represents a set per Java semantics, generally disallowing duplicate elements. Element ordering depends on the `Set` implementation used.
- `int[]` is a primitive array; the converter can turn its elements into a JSON array.
- `@Field(type = FieldType.Keyword)` declares the type of each value inside the collection. The annotation does not need a separate option to enable array mode.
- If the field type is not explicitly declared, Spring Data can infer the mapping from the property type, but for search data you should declare mappings explicitly when exact control over Elasticsearch types is required.

A Java collection does not mean Elasticsearch enforces every collection semantic. For instance, Elasticsearch does not use mappings to enforce element uniqueness in an array. If input data has duplicates, a `List` can preserve them; a `Set` deduplicates per Java rules before the converter writes the document.

Similarly, Elasticsearch can preserve array order in `_source`, but the inverted index and search structures are not designed to guarantee element ordering like a Java list. If ordering carries business meaning, read data from `_source` or represent order as an explicit numeric field.

## 3. Common Field Types Used with Multi-Valued Data

Arrays do not have a separate mapping type; the field's type remains the type of each element.

| Data in JSON | Elasticsearch mapping | Common purpose |
|---|---|---|
| `["audio", "video"]` | `keyword` | Tags, codes, categories, statuses |
| `["Spring", "Elasticsearch"]` | `text` | Multiple text snippets requiring analysis |
| `[10, 20, 30]` | `integer` or `long` | Scores, counts, numeric codes |
| `[19.5, 25.0]` | `double` or `float` | Measurements, prices, scores |
| `["2026-01-01", "2026-02-01"]` | `date` | Multiple timestamps |
| `[true, false]` | `boolean` | Multiple status flags |

For `text` arrays, Elasticsearch analyzes the values with the field's analyzer. For `keyword` arrays, each value remains a single unit for exact matching, sorting, or aggregation.

Values in an array must share the same logical data type. For instance, if a `price` field is mapped as `double`, documents must provide compatible numeric values. Do not reuse the same field to hold numbers sometimes and currency-formatted strings other times.

## 4. Querying Multi-Valued Fields

A query on a multi-valued field is generally evaluated across the values of that field. For `keyword`, `term` can match a document if at least one value in the field matches exactly.

Document example:

~~~json
{
  "name": "Wireless Headphones",
  "tags": ["audio", "bluetooth", "wireless"]
}
~~~

Query finding documents with the `bluetooth` tag:

~~~json
{
  "query": {
    "term": {
      "tags": "bluetooth"
    }
  }
}
~~~

Query finding documents with at least one tag from a list:

~~~json
{
  "query": {
    "terms": {
      "tags": ["bluetooth", "wifi", "usb"]
    }
  }
}
~~~

`terms` normally has match-any semantics across the provided values. If business rules require a document to contain at least a minimum count of values from the list, consider `terms_set` and configure the minimum match condition.

For `text` fields, a `match` query analyzes search input with the field's search analyzer:

~~~json
{
  "query": {
    "match": {
      "descriptions": "wireless noise cancellation"
    }
  }
}
~~~

If `descriptions` is a `text` field containing multiple strings, Elasticsearch indexes tokens from those values. The application still needs to select an analyzer and query type matching how users search.

For multi-valued numeric fields, a range query matches a document if any value satisfies the condition:

~~~json
{
  "query": {
    "range": {
      "ratings": {
        "gte": 5
      }
    }
  }
}
~~~

A document with `ratings: [4, 5, 5, 4]` matches because the field contains a value satisfying `gte: 5`.

## 5. Multi-Valued Fields and Sorting

When sorting by a multi-valued field, Elasticsearch needs a rule to pick a representative value. For numeric fields, you can configure `mode`:

- `min`: picks the lowest value.
- `max`: picks the highest value.
- `avg`: computes the average.
- `sum`: computes the sum.
- `median`: picks the median.

Example sorting products by highest rating:

~~~json
{
  "sort": [
    {
      "ratings": {
        "order": "desc",
        "mode": "max"
      }
    }
  ]
}
~~~

For ascending sort, the default mode is usually `min`; for descending sort, the default mode is usually `max`. Specify `mode` explicitly when the result carries specific business meaning, avoiding reliance on defaults.

For multi-valued keyword fields, `min` or `max` mode selects a value in lexicographical order. This is not necessarily the order in the JSON array. For example, an array `["wireless", "audio"]` does not mean Elasticsearch sorts by the first element.

If you need to sort by an element matching a condition—such as the price of the black variant—design an appropriate mapping and nested sort. Do not assume sorting on an object array automatically selects the right object per business conditions.

## 6. Aggregating on Multi-Valued Fields

Multi-valued keyword fields are often useful for aggregations. For example, if each product has multiple tags and the application wants to count products per tag:

~~~json
{
  "size": 0,
  "aggs": {
    "tags": {
      "terms": {
        "field": "tags"
      }
    }
  }
}
~~~

The aggregation creates buckets for tag values appearing in the data. This supports building facets or UI filters.

For multi-valued numeric fields, you can compute statistics:

~~~json
{
  "size": 0,
  "aggs": {
    "rating_stats": {
      "stats": {
        "field": "ratings"
      }
    }
  }
}
~~~

Statistics can include count, min, max, sum, and avg of the indexed values. Clarify what the statistic means: an average over every stored rating or an average of ratings already pre-aggregated at the product level. Those two data models yield different numbers.

## 7. Object Arrays and Loss of Correlation Between Properties

Simple value arrays like `tags` pose no correlation issues between elements. However, object arrays must be designed carefully.

Example of a product with multiple variants:

~~~json
{
  "name": "T-Shirt",
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

If `variants` defaults to an `object` mapping, Elasticsearch flattens the properties of the objects in the array. You can think of the indexed data as:

~~~text
variants.color = ["black", "white"]
variants.size  = ["S", "M"]
variants.stock = [0, 12]
~~~

The relationship tying `color`, `size`, and `stock` within each individual object is no longer preserved in the inverted index. As a result, a query asking for black and in-stock can accidentally match `color = black` from the first object with `stock = 12` from the second object.

Example query on a standard object:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "variants.color": "black" } },
        { "range": { "variants.stock": { "gt": 0 } } }
      ]
    }
  }
}
~~~

This query can match the document even though no single variant is both black and in stock. This is the cross-object correlation loss problem within arrays.

## 8. Using `nested` to Preserve Relationships of Each Object

If queries must require attributes to belong to the same element of an object array, use the `nested` mapping type. Elasticsearch stores each nested object as a separate internal document, allowing queries to keep scope within each individual object.

Mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "variants": {
        "type": "nested",
        "properties": {
          "color": { "type": "keyword" },
          "size": { "type": "keyword" },
          "stock": { "type": "integer" }
        }
      }
    }
  }
}
~~~

With Spring Data Elasticsearch, declare a nested collection using `@Field(type = FieldType.Nested)`:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    @Field(type = FieldType.Integer)
    private Integer stock;

    // Constructors, getters and setters
}
~~~

In the parent entity:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Nested)
    private List<ProductVariant> variants;

    // Constructors, getters and setters
}
~~~

`FieldType.Nested` helps Spring Data generate a nested mapping for the collection property. Ensure the index is created with this mapping before loading data. If the index already exists with `variants` as `object`, merely changing the annotation will not convert the existing mapping to `nested`; you typically need to create a new index and reindex data.

Nested query to find products having a variant that is black and in stock:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            { "term": { "variants.color": "black" } },
            { "range": { "variants.stock": { "gt": 0 } } }
          ]
        }
      }
    }
  }
}
~~~

Both conditions are evaluated within the same nested object. With the example data, the product does not match because the black variant has 0 stock, while the variant with 12 stock is white.

`nested` is suitable when relationships between properties of individual elements must be preserved. In return, `nested` creates extra internal documents and makes queries, aggregations, and sorting more complex. Do not use `nested` for every object array if correlation-preserving queries are not needed.

## 9. Object or Nested: Choosing by Query Pattern

| Criterion | `object` (default) | `nested` |
|---|---|---|
| How index is stored | Flattens object properties | Each object is indexed as a separate nested document |
| Preserves relationship among fields in the same object | Not preserved when querying object arrays | Preserved within a nested query scope |
| Querying | Standard field query | Requires a `nested` query with `path` |
| Indexing and query cost | Usually lower | Higher due to nested documents and scope handling |
| Best suited for | Properties not requiring per-element correlation | Variants, order lines, addresses, or members needing combined-field filters |

Examples:

- List of tags `tags: ["sale", "new"]`: use a keyword array.
- List of independent measurements `temperatures: [21.2, 22.1]`: use a numeric array.
- List of product variants, each with color, size, and stock: consider `nested` if queries require conditions to belong to the same variant.
- List of members, each with a role and status: use `nested` when checking that the same person holds both the matching role and status.

## 10. Null Values, Empty Arrays, and Missing Fields

The following cases have different meanings at the JSON and search layers:

~~~json
{
  "tags": ["audio", "wireless"],
  "emptyTags": [],
  "unknownTags": null
}
~~~

- A populated array is indexed element by element.
- An empty array creates no indexed values for the field.
- A `null` value is normally not indexed as a keyword or numeric value.
- A field absent from the document also has no indexed values.

Therefore, `exists` usually returns false when a field has no indexed values. Fields containing an empty array, `null`, or only `null` elements can be treated as non-existent from a query standpoint.

Some field types support the `null_value` option to substitute `null` with a specific value during indexing. Choose a substitute value that will not be confused with real data. `_source` still retains the original `null`; `null_value` only affects the indexed representation.

Keyword mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "status": {
        "type": "keyword",
        "null_value": "unknown"
      }
    }
  }
}
~~~

With this configuration, a document with `status: null` can be queried via the value `unknown` in the index. Do not use `null_value` if business rules need to distinguish `null`, an empty string, a missing field, and a real value.

## 11. Multi-Fields Are Not Arrays

A concept easily confused with multi-valued fields is **multi-fields**. Multi-fields allow indexing the same property under multiple different mappings. For example, a product name needs both full-text search and exact matching:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
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

The document still has a single `name` value:

~~~json
{
  "name": "Wireless Headphones"
}
~~~

However, Elasticsearch indexes that value both in `name` as `text` and in `name.keyword` as `keyword`.

Comparison:

- **Multi-valued field:** one field containing multiple values, e.g., `tags: ["audio", "wireless"]`.
- **Multi-fields:** one value indexed under multiple mappings, e.g., `name` and `name.keyword`.
- **Nested array:** a field containing multiple objects where relationships between each object's properties must be preserved.

These three concepts solve three different problems and can be combined when designing mappings.

## 12. Considerations on Size and Data Limits

Overly large arrays can increase term count, index size, indexing cost, and query latency. A document with tens of thousands or hundreds of thousands of values in a single field requires careful review of the data model.

With `nested`, each element creates an additional internal nested document. A parent document containing too many nested objects can substantially increase resource consumption and hit Elasticsearch's nested object limits. Check cluster limits and actual data sizes instead of treating Java collections as infinitely expandable.

Some design principles:

- Do not store an unbounded list inside a single document if the data can be split into independent documents.
- Only use `nested` when relationships between fields of the same element must be preserved.
- Use `keyword` for tags, codes, and classification values; use `text` for content requiring analysis.
- Clearly define the semantics of empty arrays, `null`, and missing fields.
- Enforce input bounds to prevent oversized documents.
- Test mappings and queries using data with realistic element counts.
- If element ordering carries business meaning, store position or order explicitly as a numeric field instead of relying on inverted index order.

## 13. Applying in Spring Data Elasticsearch Applications

When designing an entity, start by asking how the application will query the data:

1. If you only need to check whether a value appears in a list, use a scalar array with `keyword`, `text`, or an appropriate numeric mapping.
2. If you need to filter by any of several numbers or dates, use a multi-valued numeric/date field and a range query.
3. If each element has multiple properties that must match together, model it as an object collection with a `nested` mapping.
4. If one property needs both full-text search and exact matching, use multi-fields.
5. If statistics are needed, clarify whether aggregations operate per individual value or per document.

Spring Data Elasticsearch handles converting between the Java model and JSON documents. However, the Elasticsearch mapping still determines how values are indexed and queried. Thus, declaring `List`, `Set`, or an array in Java is not enough on its own to define search behavior; you must choose the right `FieldType`, `object` vs. `nested` mapping, and corresponding query.

A sound design clarifies three things: each element's data type, relationships among elements, and the query operations the application must execute. When these are established upfront, mapping arrays and collections from Java to Elasticsearch becomes consistent and easier to maintain.
