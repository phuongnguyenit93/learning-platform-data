# Reading Highlight, Inner Hits, Aggregation, and Suggest

Elasticsearch search results do not consist only of documents matching the query. A search response can also contain text snippets with highlighted keywords (`highlight`), child documents matching conditions within a parent document (`inner hits`), statistical results (`aggregations`), and spelling correction or autocomplete suggestions (`suggest`). Spring Data Elasticsearch groups these parts into result classes such as `SearchHit`, `SearchHits`, `ElasticsearchAggregations`, and `Suggest`.

To use these additional data elements properly, you need to distinguish which level of the response they belong to. Highlight and inner hits attach to each individual hit; aggregations and suggest reside at the level of the entire search result. They also have different mapping requirements and reading patterns. For instance, `inner_hits` usually accompanies a `nested` query and a field mapped as `nested`, aggregations require fields of appropriate types such as `keyword` or numeric, and completion suggesters require a field of type `completion`.

## 1. Search Result Structure

When calling `ElasticsearchOperations.search(...)`, Spring Data Elasticsearch returns `SearchHits<T>`. Each document matching the query is wrapped inside a `SearchHit<T>`.

```text
ElasticsearchOperations.search(query, ProductDocument.class)
                  |
                  v
             SearchHits<T>
                  |
       +----------+-----------+----------------+
       |          |           |                |
       v          v           v                v
  SearchHit   Aggregations  Suggest       Search metadata
       |
       +-- id, index, score, sort values
       +-- content (entity)
       +-- highlight fields
       +-- inner hits
```

| Data | Location in Spring Data | Meaning |
|---|---|---|
| Found document | `SearchHit.getContent()` | Entity mapped from `_source` or returned data |
| Score and identifiers | `SearchHit.getScore()`, `getId()`, `getIndex()` | Metadata of a single hit |
| Highlight | `SearchHit.getHighlightFields()` or `getHighlightField(name)` | Fragments containing query matches |
| Inner hits | `SearchHit.getInnerHits()` or `getInnerHits(name)` | Matching child documents in a nested/parent-child query |
| Aggregation | `SearchHits.getAggregations()` | Metrics and buckets aggregated across the request's document set |
| Suggest | `SearchHits.getSuggest()` | Spelling suggestions, phrase suggestions, or autocomplete |
| Total hits and duration | `SearchHits.getTotalHits()`, `getExecutionDuration()` | Overall metadata of the request |

If you return only `List<ProductDocument>`, the application typically keeps only the entity portion and loses per-hit metadata. When the UI requires highlights, inner hits, scores, aggregations, or suggestions, retain `SearchHits<T>` and convert the necessary parts into application DTOs.

## 2. Sample Document and Mapping

Suppose a product has a name, description, and multiple variants. Each variant has a color, size, and SKU. The application needs to search product content, return only variants meeting criteria, aggregate products by category, and suggest names as the user types.

```java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Nested)
    private List<ProductVariant> variants;

    @CompletionField(maxInputLength = 100)
    private Completion suggest;

    // Constructors, getters and setters
}

public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    // Constructors, getters and setters
}
```

The mapping should be designed according to query purposes:

- `name` and `description` are `text` for full-text search and highlighting.
- `name.keyword` is a `keyword` subfield, suitable for sorting or aggregating by the full name.
- `category` is `keyword`, suitable for terms aggregations.
- `price` is numeric, suitable for metric/range aggregations.
- `variants` is `nested` to preserve relationships between color, size, and SKU within each variant.
- `suggest` is `completion`, serving autocomplete.

Highlighting, aggregations, and suggestions do not fix mappings automatically. If the mapping is unsuitable, requests may fail or yield unintended results. For example, a terms aggregation on `text` is usually not the right way to group by raw values; use a `keyword` subfield instead.

## 3. What Is Highlight?

Highlighting returns one or more text snippets with the parts matching the query marked. The UI can use these fragments to emphasize keywords in titles or descriptions.

For example, when a user searches for `espresso machine`, the result might include:

```json
{
  "_id": "p-1001",
  "_source": {
    "name": "Espresso Coffee Machine"
  },
  "highlight": {
    "name": [
      "<em>Espresso</em> Coffee Machine"
    ]
  }
}
```

Highlight is supplementary hit metadata. It does not alter `_source` and is not an updated version of the document. The original content remains in `getContent()`; marked fragments reside separately in `getHighlightField(...)` or `getHighlightFields()`.

### Commonly Used Parameters

| Parameter | Effect |
|---|---|
| `pre_tags` | String placed before the matched part, e.g., `<mark>` |
| `post_tags` | String placed after the matched part, e.g., `</mark>` |
| `fragment_size` | Target size of a fragment |
| `number_of_fragments` | Maximum number of fragments returned for a field |
| `no_match_size` | Number of characters to take from the start of the field if no matching fragment is generated |
| `require_field_match` | Whether to highlight only fields participating in the query match or allow highlighting by other conditions |
| `order` | Allows sorting fragments by score |
| `type` | Selects the highlighter such as `unified`, `plain`, or `fvh` when appropriate |

If `number_of_fragments` is 0, Elasticsearch can return the entire field content instead of splitting it into fragments. This works well for short fields like titles, but can produce large responses for long descriptions.

### Highlighter Is Not an Analyzer

Analyzers produce tokens at index time and search time. Highlighters use query information and field data to determine which segments to mark. If the field's analyzer and the query analyzer differ, highlight results can be difficult to explain. Inspect the actual analyzer using `_analyze` when highlighting does not mark the expected words.

## 4. Declaring Highlight with `@Highlight`

On repository methods, you can use the `@Highlight` annotation to specify which fields to highlight. The method should return `SearchHits<T>` if per-hit metadata is needed.

```java
import org.springframework.data.elasticsearch.annotations.Highlight;
import org.springframework.data.elasticsearch.annotations.HighlightField;
import org.springframework.data.elasticsearch.annotations.HighlightParameters;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Highlight(fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    })
    SearchHits<ProductDocument> findByNameOrDescription(
            String name,
            String description);
}
```

The name in `@HighlightField(name = ...)` is the entity's property name. If the Java property name differs from the Elasticsearch field name due to `@Field(name = ...)` or a naming strategy, follow the convention required by the annotation and verify the actual mapping.

You can configure each field individually with `@HighlightParameters`, such as fragment size, number of fragments, and pre/post tags:

```java
@Highlight(fields = {
    @HighlightField(
        name = "name",
        parameters = @HighlightParameters(
            preTags = "<mark>",
            postTags = "</mark>",
            numberOfFragments = 0
        )
    ),
    @HighlightField(
        name = "description",
        parameters = @HighlightParameters(
            preTags = "<mark>",
            postTags = "</mark>",
            fragmentSize = 160,
            numberOfFragments = 3
        )
    )
})
SearchHits<ProductDocument> findByNameOrDescription(
        String name,
        String description);
```

In this example, the title returns the whole field and the description returns at most three fragments with a target size of 160 characters. Adjust the number of fragments based on the UI and desired response size.

## 5. Declaring Highlight with `NativeQuery`

When the query already uses `NativeQuery`, you can attach a `HighlightQuery` to the query builder. This approach fits well when combining highlighting with bool queries, aggregations, sorting, or other Query DSL features.

```java
import java.util.List;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.highlight.Highlight;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightField;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParametersBuilder;

HighlightParameters parameters = new HighlightParametersBuilder()
    .withPreTags("<mark>")
    .withPostTags("</mark>")
    .withFragmentSize(160)
    .withNumberOfFragments(3)
    .build();

Highlight highlight = new Highlight(
    parameters,
    List.of(
        new HighlightField("name"),
        new HighlightField("description")
    )
);

HighlightQuery highlightQuery =
    new HighlightQuery(highlight, ProductDocument.class);

Query query = NativeQuery.builder()
    .withQuery(q -> q.multiMatch(m -> m
        .query("espresso machine")
        .fields("name", "description")
    ))
    .withHighlightQuery(highlightQuery)
    .build();
```

`HighlightQuery` pairs the highlight definition with the entity type so Spring Data knows how to map fields. `Highlight`, `HighlightField`, and `HighlightParametersBuilder` reside in package `org.springframework.data.elasticsearch.core.query.highlight`; `HighlightQuery` resides in `org.springframework.data.elasticsearch.core.query`.

## 6. Reading Highlights from `SearchHit`

After executing the query:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : results.getSearchHits()) {
    ProductDocument product = hit.getContent();

    List<String> nameFragments = hit.getHighlightField("name");
    List<String> descriptionFragments = hit.getHighlightField("description");

    System.out.println(product.getName());
    System.out.println(nameFragments);
    System.out.println(descriptionFragments);
}
```

Useful accessors:

```java
Map<String, List<String>> allHighlights = hit.getHighlightFields();
List<String> nameHighlights = hit.getHighlightField("name");
```

`getHighlightFields()` returns a map from field name to a list of fragments. `getHighlightField(name)` returns the fragment list for a single field; if there are no highlights for that field, the list may be empty. Do not assume each field always has exactly one fragment.

### Rendering Highlights Safely

Tags such as `<mark>` or `<em>` are strings configured by the request. Fragment content can still contain user-supplied text. Do not insert raw fragments into HTML by unconditionally disabling escaping. Use an appropriate HTML encoder and allow only the markup tags controlled by the application. Highlighting is not an HTML sanitization or XSS protection mechanism.

### Highlights May Be Absent

Several reasons why the highlight map can be empty:

- The query did not match the requested highlight field.
- `require_field_match` retains its default behavior and the field did not participate in the match condition.
- The field does not support the chosen highlighter or required data is unavailable.
- The mapping/analyzer and query did not produce a highlightable match.
- The query only uses filters without an appropriate full-text clause.

When needed, inspect the `_search` request directly and test the highlighter on a specific document before changing the mapping.

## 7. What Are Inner Hits?

`inner_hits` returns matching child documents inside a parent document. It is especially useful for fields mapped as `nested`.

For example, a product with multiple variants:

```json
{
  "name": "Sports Jacket",
  "variants": [
    { "sku": "JKT-BLK-S", "color": "black", "size": "S" },
    { "sku": "JKT-BLK-L", "color": "black", "size": "L" },
    { "sku": "JKT-WHT-M", "color": "white", "size": "M" }
  ]
}
```

If using a `nested` query looking for `color = black` and `size = L`, Elasticsearch can return the parent product document along with specifically the `JKT-BLK-L` variant inside `inner_hits`. The application knows exactly which element in the array caused the parent document to match.

### Why Must `nested` Be Used?

Regular object arrays are flattened by Elasticsearch during indexing. That can cause conditions on attributes belonging to different objects to be cross-matched. `nested` stores each element as an independent child document, preserving relationships among fields within the same element.

Simply declaring `inner_hits` in a query is not enough. The field must be mapped as `nested` if you want semantically accurate nested queries.

## 8. Nested Mapping in Spring Data

Declare the array property using `FieldType.Nested`:

```java
public class ProductVariant {

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String color;

    @Field(type = FieldType.Keyword)
    private String size;

    // Constructors, getters and setters
}

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
```

Corresponding JSON mapping:

```json
{
  "properties": {
    "name": { "type": "text" },
    "variants": {
      "type": "nested",
      "properties": {
        "sku": { "type": "keyword" },
        "color": { "type": "keyword" },
        "size": { "type": "keyword" }
      }
    }
  }
}
```

The mapping of an existing index must genuinely be `nested`. Changing the Java annotation after the index has already been created does not automatically convert an `object` field into `nested`; this change generally requires a new index and reindexing data.

## 9. Declaring a Nested Query with Inner Hits

With the Elasticsearch Java API Client, you can use `NativeQuery` and a nested query. Naming inner hits helps read the right group when a query has multiple nested paths.

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.nested(n -> n
        .path("variants")
        .query(nq -> nq.bool(b -> b
            .must(m -> m.term(t -> t
                .field("variants.color")
                .value("black")
            ))
            .must(m -> m.term(t -> t
                .field("variants.size")
                .value("L")
            ))
        ))
        .innerHits(ih -> ih
            .name("matching_variants")
            .size(5)
        )
    ))
    .build();
```

This query finds parent documents having at least one variant that is both black and size L, then returns up to five matching nested hits in the group named `matching_variants`.

Conceptually equivalent JSON Query DSL:

```json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "must": [
            { "term": { "variants.color": "black" } },
            { "term": { "variants.size": "L" } }
          ]
        }
      },
      "inner_hits": {
        "name": "matching_variants",
        "size": 5
      }
    }
  }
}
```

Field names in Query DSL are Elasticsearch field names, including the `variants.` path. The name `matching_variants` is an application-defined response label, not a mapped field.

## 10. Reading Inner Hits from `SearchHit`

`SearchHit<T>` provides `getInnerHits()` to get a map of inner hit groups or `getInnerHits(name)` to get a specific group.

```java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> parentHit : results.getSearchHits()) {
    ProductDocument product = parentHit.getContent();

    SearchHits<?> matchingVariants =
        parentHit.getInnerHits("matching_variants");

    if (matchingVariants == null) {
        continue;
    }

    for (SearchHit<?> variantHit : matchingVariants.getSearchHits()) {
        Object variant = variantHit.getContent();
        System.out.println(product.getName());
        System.out.println(variant);
    }
}
```

`getInnerHits(name)` can return `null` if the group does not exist on that hit. If Spring Data can map the inner hit to the nested entity type, `getContent()` may be `ProductVariant`; otherwise, the content may be returned as `SearchDocument`. When a specific type is required, check the actual mapped type and avoid unchecked casts.

All inner hit groups can be retrieved with:

```java
Map<String, SearchHits<?>> allInnerHits = parentHit.getInnerHits();
```

Each parent hit can have a different number of inner hits. Inner hits can carry their own metadata such as score, highlights, and sort values.

## 11. Combining Inner Hits and Highlight

An application may need to highlight keywords inside the matching nested object itself. In that case, place `highlight` inside the `inner_hits` section of the nested query.

REST DSL example:

```json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "match": {
          "variants.description": "waterproof"
        }
      },
      "inner_hits": {
        "name": "matching_variants",
        "highlight": {
          "fields": {
            "variants.description": {
              "pre_tags": ["<mark>"],
              "post_tags": ["</mark>"]
            }
          }
        }
      }
    }
  }
}
```

After reading `parentHit.getInnerHits("matching_variants")`, call `getHighlightField("variants.description")` on each nested `SearchHit` if that highlight part is mapped by Spring Data in the response. Verify field names against the actual mapping and response; nested fields may appear with their full path.

## 12. What Is Aggregation?

Aggregations summarize data over the set of documents matching a query. They can compute overview metrics or group documents into buckets.

| Type | Examples | Result |
|---|---|---|
| Metric | `avg`, `sum`, `min`, `max`, `stats`, `cardinality` | Statistical values |
| Bucket | `terms`, `range`, `date_histogram`, `filters` | Document groups with `doc_count` |
| Sub-aggregation | `terms` containing `avg` or `sum` | Child statistics inside each bucket |
| Pipeline | `derivative`, `moving_fn`, `bucket_script` | Computations based on other aggregation results |

For example, counting products by category and computing average price:

```json
{
  "size": 0,
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category",
        "size": 20
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
```

`size: 0` requests no document hits to be returned, while aggregations are still computed and returned. This is useful for dashboards that only need metrics.

## 13. Declaring Aggregations with `NativeQuery`

Spring Data Elasticsearch uses `NativeQuery` to declare aggregations from the Elasticsearch Java API Client.

```java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withAggregation(
        "products_by_category",
        Aggregation.of(a -> a.terms(t -> t
            .field("category")
            .size(20)
        ).aggregations(
            "average_price",
            Aggregation.of(sub -> sub.avg(avg -> avg.field("price")))
        ))
    )
    .build();
```

`products_by_category` and `average_price` are application-assigned aggregation names. Use these exact names when reading results. The `category` field requires a `keyword` mapping; the `price` field requires a numeric mapping.

You can combine a filtering query with aggregations. The top-level query restricts the input document set for both hits and regular aggregations:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.term(t -> t
        .field("status")
        .value("PUBLISHED")
    ))
    .withAggregation(
        "products_by_category",
        Aggregation.of(a -> a.terms(t -> t.field("category").size(20)))
    )
    .build();
```

Here, buckets are computed only over products with `status = PUBLISHED`.

## 14. Reading Aggregations from `SearchHits`

`SearchHits.getAggregations()` returns an `AggregationsContainer<?>`. With ELC, Spring Data provides `ElasticsearchAggregations` to access results by name.

```java
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregation;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchAggregations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasAggregations()
        && results.getAggregations() instanceof ElasticsearchAggregations aggregations) {

    ElasticsearchAggregation categoryAggregation =
        aggregations.get("products_by_category");

    var categoryTerms = categoryAggregation.aggregation().sterms();

    for (var bucket : categoryTerms.buckets().array()) {
        String category = bucket.key().stringValue();
        long productCount = bucket.docCount();
        double averagePrice = bucket.aggregations()
            .get("average_price")
            .avg()
            .value();
    }
}
```

`sterms()` is the terms variant for string keys. For numeric fields, the aggregate type may be `lterms()` or `dterms()`. An `avg` metric returns an aggregate with `value()`. Choose the accessor matching the declared aggregation type and field type; do not cast every aggregate to the same type.

If only summary metrics are needed, such as `stats`:

```java
Query query = NativeQuery.builder()
    .withAggregation(
        "price_stats",
        Aggregation.of(a -> a.stats(s -> s.field("price")))
    )
    .build();

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.getAggregations() instanceof ElasticsearchAggregations aggregations) {
    var stats = aggregations.get("price_stats").aggregation().stats();
    long count = stats.count();
    double min = stats.min();
    double max = stats.max();
    double average = stats.avg();
    double sum = stats.sum();
}
```

## 15. Filter Scope of Aggregations

Distinguish between the top-level query, `filter` aggregation, and `post_filter`:

- The top-level query limits the input document set for both hits and aggregations.
- A `filter` aggregation creates a separate child bucket containing only documents matching its condition.
- `post_filter` filters hits after aggregations have been computed; it does not change the input document set for aggregations.

For example, returning hits for available products while computing category counts across all products:

```json
{
  "post_filter": {
    "term": {
      "available": true
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
```

In this example, `post_filter` affects the hit list, while the `by_category` aggregation is still computed over the document set prior to the post-filter. If aggregations should also count only available products, place the condition in the top-level query or use an appropriate filter aggregation.

### Terms Aggregation Does Not Automatically Return All Buckets

`terms.size` limits the number of returned buckets, usually used for top N. When iterating over a large number of buckets or all combinations is needed, consider a `composite` aggregation with `after_key` pagination. Do not set an arbitrarily huge `size` without evaluating memory and cluster load.

## 16. What Is Suggest?

Suggest returns suggestions related to user-entered text. It is commonly used for spelling correction, phrase suggestions, or autocomplete.

| Suggester | Purpose | Example |
|---|---|---|
| `term` | Proposes replacement terms based on edit distance | `elastcsearch` → `elasticsearch` |
| `phrase` | Proposes entire phrases based on statistical/context models | `noble prize` → `nobel prize` |
| `completion` | Fast prefix-based autocomplete | `iph` → `iPhone` |
| Context completion | Autocomplete filtered or boosted by context | Suggesting places by category or location |

Suggest is a separate section in the search response. One request can both run a query for document hits and run a suggester to return suggestions. With a term suggester, suggestions are based on the specified text and field; they are not necessarily restricted by the accompanying document query.

## 17. Term Suggester and Phrase Suggester

### Term Suggester

The term suggester analyzes input text and finds likely correct spellings based on edit distance. It operates token by token, so it can return multiple entries for a query string.

Example REST DSL:

```http
POST /products/_search
Content-Type: application/json

{
  "suggest": {
    "name_terms": {
      "text": "wireles hedphones",
      "term": {
        "field": "name",
        "suggest_mode": "popular",
        "size": 5
      }
    }
  }
}
```

`suggest_mode` can be `missing`, `popular`, or `always`. The mode controls when input terms are considered for suggestions. The selected field must have appropriate tokens and a language-appropriate analyzer.

### Phrase Suggester

The phrase suggester combines candidate generators with n-gram statistics to select corrections for the entire phrase, rather than proposing independent replacements for each token. It typically requires an n-gram field or appropriate mapping/analyzer configuration.

Example REST DSL:

```json
{
  "suggest": {
    "name_phrase": {
      "text": "wireles hedphones",
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "always"
          }
        ],
        "highlight": {
          "pre_tag": "<mark>",
          "post_tag": "</mark>"
        }
      }
    }
  }
}
```

The phrase suggester is suited for “Did you mean…?” when users mistype an entire phrase. It should be tested with real data because candidate generation and n-gram statistics strongly impact suggestion quality.

## 18. Completion Suggester for Autocomplete

The completion suggester is optimized for low-latency prefix queries. The field used for suggestions must be mapped with type `completion`.

Example JSON mapping:

```json
{
  "properties": {
    "suggest": {
      "type": "completion",
      "analyzer": "simple",
      "search_analyzer": "simple",
      "preserve_separators": true,
      "preserve_position_increments": true,
      "max_input_length": 100
    }
  }
}
```

Spring Data Elasticsearch supports `@CompletionField` and the `Completion` type:

```java
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@CompletionField(
    analyzer = "simple",
    searchAnalyzer = "simple",
    maxInputLength = 100
)
private Completion suggest;
```

When saving a product, provide candidate strings to suggest:

```java
product.setSuggest(new Completion(new String[] {
    "iPhone 16",
    "Apple iPhone 16 Pro",
    "iPhone 16 Pro Max"
}));
```

Weights can be used to prioritize certain suggestions if the `Completion` type and API version in use support corresponding configuration. Completion fields are optimized for fast lookup and use in-memory data structures; monitor completion index size when storing many inputs.

### Querying Completion via REST

```http
POST /products/_search
Content-Type: application/json

{
  "_source": ["name", "category"],
  "suggest": {
    "product_autocomplete": {
      "prefix": "iph",
      "completion": {
        "field": "suggest",
        "size": 5,
        "skip_duplicates": true
      }
    }
  }
}
```

`prefix` is the string typed by the user. `size` limits the number of suggestions and `skip_duplicates` removes duplicate suggestions. The completion suggester is not a spelling corrector; if spell-checking is needed, consider term or phrase suggesters.

## 19. Declaring Suggest with `NativeQuery`

`NativeQueryBuilder` supports `withSuggester(...)`, accepting a `Suggester` from the Elasticsearch Java API Client.

Term suggester example:

```java
import co.elastic.clients.elasticsearch.core.search.FieldSuggester;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Suggester suggester = Suggester.of(s -> s
    .text("wireles hedphones")
    .suggesters("name_terms", FieldSuggester.of(fs -> fs
        .term(t -> t
            .field("name")
            .size(5)
        )
    ))
);

Query query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
```

You can add `withQuery(...)` if the same request needs to return document hits and suggestions. `withSuggester(...)` uses the ELC API; do not confuse it with `RestHighLevelClient` configurations in older integration generations.

Completion suggester example:

```java
Suggester suggester = Suggester.of(s -> s
    .suggesters("product_autocomplete", FieldSuggester.of(fs -> fs
        .prefix("iph")
        .completion(c -> c
            .field("suggest")
            .size(5)
            .skipDuplicates(true)
        )
    ))
);

Query query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
```

Builder names and enum types of the Java API Client are generated according to the client version managed by Spring Data. If the IDE does not recognize a method, check the actual ELC version and corresponding Javadoc, and do not mix imports from older clients.

## 20. Reading Suggest from `SearchHits`

Suggest results reside at the `SearchHits` level, not inside an individual `SearchHit`:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasSuggest()) {
    Suggest suggest = results.getSuggest();
    Suggest.Suggestion<?> nameSuggestion =
        suggest.getSuggestion("name_terms");

    if (nameSuggestion != null) {
        for (Suggest.Suggestion.Entry<?> entry : nameSuggestion.getEntries()) {
            String originalToken = entry.getText();

            for (Suggest.Suggestion.Entry.Option option : entry.getOptions()) {
                String candidate = option.getText();
                Double score = option.getScore();
            }
        }
    }
}
```

`Suggest.getSuggestion(name)` retrieves the suggestion by the name declared in the request. Each suggestion can contain multiple entries; each entry can contain multiple options. An entry's `getText()` is the input token/phrase, whereas an option's `getText()` is the proposed candidate. Certain option types also include score, highlighted text, document frequency, or dedicated metadata.

For term suggestions, `TermSuggestion.Entry.Option` additionally provides `getFreq()`. For completion suggestions, an option may include the corresponding hit/document information. Read according to the suggester type when specialized metadata is needed.

## 21. Combining Highlight, Aggregation, and Suggest in One Search

A single request can include multiple result components simultaneously:

- Query searching products by content.
- Highlight marking matched words in name/description.
- Aggregation counting products by category.
- Suggest proposing spelling corrections or autocomplete.

Simplified REST DSL example:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "multi_match": {
      "query": "wireless headphones",
      "fields": ["name", "description"]
    }
  },
  "highlight": {
    "fields": {
      "name": { "number_of_fragments": 0 },
      "description": {
        "fragment_size": 160,
        "number_of_fragments": 2
      }
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 10
      }
    }
  },
  "suggest": {
    "name_terms": {
      "text": "wireles hedphones",
      "term": {
        "field": "name",
        "size": 5
      }
    }
  }
}
```

In the response, highlights reside inside each hit, aggregations reside in `aggregations`, and suggestions reside in `suggest`. The top-level query determines the searched document set and is also the input set for aggregations. The term suggester uses its own suggest text and field to generate candidates.

When implementing with `NativeQuery`, you can combine `withQuery`, `withHighlightQuery`, `withAggregation`, and `withSuggester` on the same builder. Then read each part from `SearchHits` at its corresponding data level.

## 22. Distinguishing Inner Hits and Aggregations

These two features are sometimes confused because both return extra information inside search results:

| Criterion | Inner hits | Aggregation |
|---|---|---|
| Goal | Return specific matching child documents | Aggregate or group multiple documents |
| Scope | Attached to each parent hit | Attached to the entire search response or buckets |
| Returned data | Nested/child hits with metadata | Metrics and buckets such as count, sum, avg |
| Example | Black, size L variants of a product | Number of products by category |
| How to read | `SearchHit.getInnerHits(name)` | `SearchHits.getAggregations()` |

If the UI needs to display each matching variant, use inner hits. If facet filters or counts by category are needed, use aggregations. Both can be combined in the same request when genuinely required.

## 23. Distinguishing Highlight and Suggest

Highlight marks matched text within returned documents. Suggest proposes alternative text or continuations the user can choose.

| Criterion | Highlight | Suggest |
|---|---|---|
| Used when | The user has found documents and needs to see where matches occurred | The user needs spelling corrections or query completion |
| Data source | Fields inside document hits | Fields configured for suggester or completion |
| Result | Text fragments | Suggestion candidates and metadata |
| Spring Data location | `SearchHit.getHighlightField(s)` | `SearchHits.getSuggest()` |
| Dedicated mapping needed? | Depends on highlighter and field; typically indexed `text` fields | Completion requires a `completion` field; term/phrase require appropriate fields and analyzers |

A good search experience can use suggest before the user submits a query, highlight once results arrive, and aggregations to provide filtering facets.

## 24. Performance and Limits to Watch

### Highlight

- Highlight only fields that the UI actually renders.
- Limit fragment count and fragment size for long fields.
- Use `number_of_fragments: 0` deliberately for short fields.
- Highlighters may need access to `_source`, postings, or term vectors depending on type; choose mappings suited to the workload.
- Avoid requesting many long fields in a query with a large hit count.

### Inner hits

- Limit `inner_hits.size` because each parent hit can return multiple child hits.
- Fetch only necessary fields from nested documents.
- Use `nested` when preserving element relationships is required; do not convert every object into `nested` because `nested` has storage and query costs.
- Note that parent hit pagination and the number of inner hits per parent are two separate limits.

### Aggregation

- Use `keyword`, numeric, or date fields with proper mappings.
- Limit bucket count and sub-aggregation depth.
- `terms.size` only returns top buckets; use `composite` when paginating through many buckets.
- `cardinality` is typically approximate, not exact distinct counts by default.
- Use `size: 0` when only aggregations are needed, avoiding unnecessary hit transfers.

### Suggest

- Limit candidate `size`.
- Completion fields use in-memory data structures; monitor size and input count.
- Context completion increases memory footprint and requires consistent contexts at both index and query time.
- Term/phrase suggesters rely on appropriate analyzers and vocabulary data; they are not perfect spell-checkers.
- For autocomplete, debounce client requests and only send prefixes of sufficient length to reduce load.

## 25. Testing and Diagnostics

When a supplementary result section does not appear, inspect layer by layer.

| Symptom | What to check |
|---|---|
| Empty highlight | Whether the field matched the query, field name, analyzer, highlighter type, and fragment count |
| Wrong highlight snippet | Actual query, analyzer, `require_field_match`, matched fields, and `_source` content |
| Missing inner hits | Whether mapping is `nested`, nested path, whether query matched child documents, and inner hits name |
| Inner hits not mapped to entity | Nested class type, mapping metadata, and actual `SearchHit<?>` type |
| Empty aggregation | Field mapping, query filter, aggregation name, and `hasAggregations()` |
| Missing buckets | `terms.size`, `shard_size`, cardinality, or whether a composite aggregation is needed |
| Suggest returns no candidates | Suggester field, analyzer, completion mapping, or input text |
| Completion returns duplicates | `skip_duplicates`, input data, and context mapping |

Useful APIs for inspection:

```http
GET /products/_mapping
```

```http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "wireless headphones"
}
```

Run the search request directly in Elasticsearch Dev Tools first to verify the JSON response includes `highlight`, `inner_hits`, `aggregations`, or `suggest`. Then cross-check with Spring Data accessors. This isolates Query DSL structural errors from Java response-mapping errors.

In integration tests, use a pinned Elasticsearch version compatible with the project's Spring Data/client. Load fixtures, refresh indices when needed so searches see the data, and assert both document hits and supplementary metadata. Do not assert only that the repository returns a document; assert the corresponding highlight fragments, inner hit IDs, bucket counts, or suggestion options.

## 26. Converting Results to DTOs for APIs

You do not need to return raw `SearchHits`, `ElasticsearchAggregations`, or Spring Data suggest classes directly out of a REST API. Create DTOs containing only the data the UI needs.

Example:

```java
public record ProductSearchItem(
        String id,
        String name,
        List<String> nameHighlights,
        List<String> descriptionHighlights,
        List<ProductVariant> matchingVariants,
        float score) {
}

public record CategoryFacet(String category, long count) {
}

public record ProductSearchResponse(
        List<ProductSearchItem> items,
        List<CategoryFacet> categories,
        List<String> suggestions,
        long totalHits) {
}
```

The service can convert each `SearchHit` into `ProductSearchItem`, read `getInnerHits("matching_variants")` for variants, convert aggregation buckets into `CategoryFacet`, and convert suggest options into a list of strings. DTOs clarify the API contract and prevent the frontend from depending on ELC types.

When mapping highlights into DTOs, still enforce safe HTML handling at the display layer. If the frontend receives fragments containing markup tags, clearly specify allowed tags and encode untrusted text segments.

## 27. Workflow for Implementing a Search Results Page

A product search page can be built in this order:

1. Design the mapping: text/keyword/numeric fields, nested variants, and a completion field if autocomplete is needed.
2. Build the main query to find products and define mandatory filters.
3. Add highlights for titles/descriptions displayed by the UI.
4. Add a nested query with inner hits if returning exact matching variants is required.
5. Add aggregations to compute facets by category or price range.
6. Add suggest for spelling correction or autocomplete according to UX goals.
7. Execute via `ElasticsearchOperations.search(...)` with `NativeQuery`.
8. Read hit metadata via `SearchHit`, aggregations via `SearchHits.getAggregations()`, and suggestions via `SearchHits.getSuggest()`.
9. Convert results into DTOs with a stable structure.
10. Test edge cases, mappings, responses, and request cost against a compatible Elasticsearch instance.

## 28. Conclusion

Spring Data Elasticsearch provides a unified result model for reading extensions of the search response. Highlights and inner hits attach to each `SearchHit`; aggregations and suggestions reside at the `SearchHits` level. Use `@Highlight` for simple repository methods or `HighlightQuery` in `NativeQuery` when flexible queries are required. Use nested mappings and nested queries with `inner_hits` when exact matching child elements need to be returned. Use `withAggregation(...)` to declare metrics/buckets and read them via `ElasticsearchAggregations`. Use `withSuggester(...)` to declare term, phrase, or completion suggesters and retrieve results via `SearchHits.getSuggest()`.

Each feature has specific mapping and processing requirements: highlights return fragments rather than modifying source, inner hits require matching nested paths, aggregations depend on field types and query scope, and completion requires an indexed `completion` field. By maintaining clear boundaries among response components, verifying mappings, and translating data into explicit DTOs, an application can deliver rich search pages while keeping performance and API structure under control.

## References

- [Spring Data Elasticsearch – Search result types and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – Repository `@Highlight`](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repositories.html)
- [Spring Data Elasticsearch – `SearchHit` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHit.html)
- [Spring Data Elasticsearch – `SearchHits` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Spring Data Elasticsearch – `NativeQueryBuilder` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Elasticsearch – Highlighting](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/highlighting)
- [Elasticsearch – Nested query and inner hits](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-nested-query)
- [Elasticsearch – Search suggesters](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters)
- [Elasticsearch – Aggregations](https://www.elastic.co/docs/explore-analyze/query-filter/aggregations)
