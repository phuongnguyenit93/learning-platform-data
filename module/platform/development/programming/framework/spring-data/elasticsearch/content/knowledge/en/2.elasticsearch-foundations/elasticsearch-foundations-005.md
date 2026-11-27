# Distinguishing `text`, `keyword`, and their intended uses

In Elasticsearch, a string does not inherently carry the meaning of "text for searching" or "a value for comparison". The **mapping** determines how Elasticsearch analyzes, indexes, and queries that string. The two most important data types for strings are `text` and `keyword`.

When designing entities with Spring Data Elasticsearch, choosing the right data type yields accurate search results while supporting filtering, sorting, and statistics without sacrificing memory or performance.

## 1. Core differences

| Criterion | `text` | `keyword` |
|---|---|---|
| Purpose | Search content by words or phrases | Store and compare the entire value |
| String analysis | Yes, via an analyzer | Not split into tokens; can be normalized with a normalizer |
| How it is indexed | Usually produces multiple tokens from one string | Indexes a single token representing the entire value |
| Common queries | `match`, `match_phrase` | `term`, `terms` |
| Best suited for | Full-text search and relevance scoring | Exact matching, filtering, grouping, and sorting |
| Sorting / aggregation | Not suitable by default | Suitable |
| Examples | Product descriptions, article bodies | SKU codes, statuses, categories, emails |

Consider the string:

`Spring Data Elasticsearch`

- With `text`, an analyzer can split the string into tokens such as `spring`, `data`, and `elasticsearch`. A user searching for `elasticsearch` can still find documents containing the original phrase.
- With `keyword`, the entire string is treated as a single value. Querying for `Spring Data Elasticsearch` can match the whole value; querying for `elasticsearch` alone does not search for a word inside the string.

This is a difference in how data is indexed, not merely a difference in query syntax.

## 2. `text`: designed for full-text search

### What does an analyzer do?

When a `text` value is indexed, Elasticsearch passes it through an **analyzer**. An analyzer typically consists of three stages:

1. **Character filters**: transform or strip characters before word splitting, such as handling certain HTML markup.
2. **Tokenizer**: splits the string into tokens according to language rules.
3. **Token filters**: modify tokens, such as lowercasing, normalizing, or removing stop words if configured.

For example, the `standard` analyzer typically splits text on word boundaries and lowercases tokens. Therefore, the content `Spring Data Elasticsearch` can be found using `spring` or `data`.

The analyzer determines how content is stored in the inverted index. The search-time analyzer matters as well: Elasticsearch typically analyzes the query phrase using the corresponding search analyzer before looking up indexed tokens.

### Suitable query types

**`match`** is the standard choice for full-text search. Elasticsearch analyzes the query input and searches for matching tokens:

~~~json
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  }
}
~~~

Documents with matching tokens can be returned and scored for relevance. How tokens are combined depends on query options such as `operator` or `minimum_should_match`.

**`match_phrase`** is used when the order and position of tokens in a phrase matter:

~~~json
{
  "query": {
    "match_phrase": {
      "description": "spring data"
    }
  }
}
~~~

This query searches for a sequence of tokens in the right order and proximity, rather than requiring words to appear separately anywhere.

### Why not use `text` for every string?

`text` is optimized for content search. It is not a good default choice for identifiers, statuses, or values needing exact comparison.

A `term` query does not analyze input the way `match` does. If a `text` field has already been split into lowercase tokens, a `term` query with the original string usually will not match as expected. A `term` query with an exact indexed token can still match, but that does not make `text` suitable for whole-value matching.

Additionally, `text` does not enable `fielddata` by default. As a result, sorting or aggregating directly on a `text` field is typically unavailable. `fielddata` can be enabled, though doing so can consume significant heap memory; usually, a separate `keyword` field should be used for those operations.

## 3. `keyword`: designed for exact, whole values

`keyword` is appropriate when the application needs to treat the entire string as a single value:

- `status = PUBLISHED`
- `category = LAPTOP`
- `sku = KB-1001`
- `email = user@example.com`
- `countryCode = VN`

A `keyword` field does not go through word tokenization like `text`. By default, uppercase and lowercase letters are distinct. If normalization is needed, a **normalizer** can be configured. A normalizer transforms the value while keeping it as a single token; for example, it can lowercase text so matching does not depend on letter case.

### Exact queries

Use `term` when matching a single value:

~~~json
{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

Use `terms` when matching one of multiple values:

~~~json
{
  "query": {
    "terms": {
      "status": ["PUBLISHED", "APPROVED"]
    }
  }
}
~~~

With `keyword`, these queries compare against the indexed value. If the field uses a normalizer, keep in mind that values are normalized before comparison.

### Sorting and statistics

`keyword` is suitable for operations such as sorting by name, counting documents by status, or grouping products by category:

~~~json
{
  "sort": [
    {
      "sku": {
        "order": "asc"
      }
    }
  ],
  "aggs": {
    "products_by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
~~~

`keyword` fields typically have doc values to support sorting and aggregations efficiently. If string values can be very long and the mapping uses `ignore_above`, check that limit: values exceeding the limit may remain in `_source` without being indexed in the corresponding keyword field.

## 4. A property needing both full-text search and exact matching: multi-fields

Product names are a classic example. Users may want to:

- Search products by part of a name or words within the name.
- Sort products by name.
- Filter by an exact name.
- Group or compute statistics by name.

If declared only as `text`, full-text search works nicely, but sorting and aggregations run into limitations. If declared only as `keyword`, whole-value matching works well, but word-by-word search does not fit.

**Multi-fields** solve this by indexing the same property under multiple data types. For example, the `name` field has a main `text` field and a sub-field `name.keyword` of type `keyword`.

The corresponding mapping looks like:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
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

These two fields have distinct roles:

| Field | Used for |
|---|---|
| `name` | `match`, `match_phrase`, content-based search |
| `name.keyword` | `term`, exact filtering, sorting, aggregation |

The name `keyword` is a common convention, not a mandatory Elasticsearch rule. The sub-field name depends on the mapping the application declares.

## 5. Declaring mappings with Spring Data Elasticsearch

Spring Data Elasticsearch provides annotations to describe mappings from Java entities. You can use `@Field` to select a specific data type.

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
    private String name;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructors, getters and setters
}
~~~

In the example:

- `name` is a multi-field. Spring Data describes the main field as `text` and the sub-field `name.keyword` as `keyword`.
- `description` uses `text` because content search is needed.
- `status` and `category` use `keyword` because they are typically filtered or grouped by value.

`@Id` marks the Spring Data entity identifier. This identifier serves document mapping; do not confuse it with choosing `text` or `keyword` for other business properties.

If you want to use a normalizer for a keyword field, declare the normalizer in index settings before creating the index, and then reference the normalizer name in the mapping. You cannot simply change how queries are written in the repository and expect existing data to be reindexed under new rules.

## 6. Using the right field when querying

Suppose the `Product` entity has the mapping from the previous section.

### Searching by name or description

Use the `text` field:

~~~json
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

The query will be analyzed using the field's analyzer and searched by tokens.

### Filtering by status

Use the `keyword` field:

~~~json
{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

### Finding an exact full name

Use the `name.keyword` sub-field:

~~~json
{
  "query": {
    "term": {
      "name.keyword": "Wireless Keyboard"
    }
  }
}
~~~

### Sorting by name

Use the `name.keyword` sub-field:

~~~json
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

### Combining search and filtering

A real-world requirement might both search products by content and restrict results to published products:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
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

In this example, `must` holds the full-text search condition that can affect relevance score; `filter` holds exact filter conditions that are not used to calculate relevance scores. Choosing the right field for each condition keeps queries clear and leverages proper indexing.

## 7. Common design mistakes

### Using `text` for statuses or codes

If `status` is declared as `text`, the string may be analyzed into tokens. Using `term` with the raw status value may not yield expected results. Use `keyword` for statuses, codes, enums, country codes, and values requiring whole-value matching.

### Using `keyword` for long content needing word-based search

A long description stored as `keyword` is treated as a single value. Users searching for a word inside the description will not get expected full-text search behavior. Use `text` for content that needs analysis.

### Using `text` for sorting or aggregations

Sorting or aggregations on `text` are typically rejected because `fielddata` is disabled by default. Do not enable `fielddata` just as a quick workaround when an appropriate `keyword` multi-field can be created.

### Using `name` instead of `name.keyword`

With multi-fields, `name` and `name.keyword` are two separately indexed fields. Full-text search uses `name`; exact filtering, sorting, and aggregations use `name.keyword`. Choosing the wrong field can cause query errors or unexpected results.

### Changing the data type of an existing field

You cannot directly change an already indexed field from `text` to `keyword` by editing an annotation and expecting the existing index to convert its data automatically. You must create a new index with the right mapping, reindex the data, and switch the application to the new index following an appropriate deployment process.

When adding a multi-field to an existing mapping, older documents also do not automatically gain indexed values for the new sub-field. You need to reindex or update older documents so the sub-field is populated.

## 8. Rules for choosing a data type

You can use the following questions when designing an entity:

1. Do users need to search for a word or phrase inside the content? Choose `text`.
2. Does the application need to compare the entire value, such as status, code, category, or email? Choose `keyword`.
3. Does the same property need both full-text search and exact filtering/sorting? Use multi-fields with a `text` main field and a `keyword` sub-field.
4. Do you need to ignore case differences when matching keywords? Configure an appropriate normalizer and create the mapping/index with that configuration.
5. Do you need sorting or aggregations? Verify the query uses a `keyword` field, often the sub-field of a multi-field.

| Business data | Typically suitable mapping | Reason |
|---|---|---|
| `description`, `content` | `text` | Full-text search |
| `title`, `name` | Multi-field: `text` + `keyword` | Word-based search and exact sorting/filtering |
| `status`, `type` | `keyword` | Finite categorical values |
| `sku`, `code` | `keyword` | Codes that must remain intact |
| `category`, `tags` | `keyword` | Filtering and aggregations |
| `email` | `keyword` | Matching the full address |

There is no rule that every Java `String` property must be `text`. The Java type only represents data in the application; the Elasticsearch mapping must reflect how the data is searched and used.

## Conclusion

`text` and `keyword` serve two different query models. `text` analyzes strings into tokens for full-text search; `keyword` keeps the entire value as a single unit for matching, filtering, sorting, and statistics. In Spring Data Elasticsearch, declare mappings explicitly with `@Field`; use `@MultiField` when a single property requires both usages.
