# Building Product Search with Text, Keyword, and Multi-Field

A product search screen often needs multiple ways of interpreting the same value. For a product name, users may enter part of the name for full-text search, need an exact match when selecting a specific product, sort by name, and aggregate by brand. If you declare only a single `text` or `keyword` field, some operations will not fit or will force a trade-off between accuracy and searchability.

Elasticsearch solves this problem by distinguishing two primary field types:

- **`text`**: analyzes content into tokens for full-text search, supporting analyzers, stemming, stop words, and phrase queries.
- **`keyword`**: keeps the value as a single term for exact matching, filtering, sorting, and aggregations.

**Multi-field** lets you index the same value under multiple representations. For example, `name` is a `text` field for keyword search, while `name.keyword` is a `keyword` subfield for exact match, sorting, and aggregations. Both fields read data from the same source attribute without requiring two copies of the name to be stored in the JSON document.

This lesson builds a search model for products, designs the mapping, configures Spring Data Elasticsearch, writes full-text and exact-match queries, combines relevance scores with filters, and explains how to evolve the mapping when the index already contains data.

## 1. Starting from Product Search Requirements

Suppose a product document contains the following data:

~~~json
{
  "productId": "KB-1001",
  "sku": "KB-1001-BLK",
  "name": "Wireless Mechanical Keyboard",
  "description": "Compact keyboard with hot-swappable switches",
  "brand": "KeyWorks",
  "category": "ACCESSORIES",
  "tags": ["wireless", "mechanical", "keyboard"],
  "status": "PUBLISHED",
  "priceMinor": 1299000,
  "updatedAt": "2026-11-13T08:30:00Z"
}
~~~

A search API may need to support these operations:

| Requirement | Example | Appropriate field |
|---|---|---|
| Search keywords in name | `mechanical keyboard` | `name` of type text |
| Search keywords in description | `hot-swappable` | `description` of type text |
| Exact match SKU | `KB-1001-BLK` | `sku` of type keyword |
| Exact match name | `Wireless Mechanical Keyboard` | `name.keyword` |
| Filter by brand | `brand = KeyWorks` | `brand` of type keyword |
| Sort by name | A → Z | `name.keyword` |
| Aggregate by brand | Count products per brand | `brand` of type keyword |
| Search across multiple fields | Name or description | `multi_match` on text fields |

A field does not necessarily serve only one operation. Multi-field allows you to keep a single source value while indexing it with multiple different semantics.

## 2. How Do Text and Keyword Differ?

### Text: Analyzed Content

When indexing a `text` field, Elasticsearch runs an analyzer. An analyzer typically consists of:

1. Character filters: transform the input string before tokenization.
2. Tokenizer: splits the string into tokens.
3. Token filters: lowercase, stemming, stop-word filtering, or other transformations.

For example, the standard analyzer may turn:

~~~text
Wireless Mechanical Keyboard
~~~

into tokens roughly like:

~~~text
wireless
mechanical
keyboard
~~~

The tokens are written into an inverted index for searching. A `match` query also analyzes the input using the search analyzer and then looks up matching tokens.

Therefore, `text` is well suited for:

- Searching for one or more words in a sentence.
- Searching for phrases using a phrase query.
- Searching across multiple text fields.
- Calculating a relevance score.
- Stemming or language-specific analyzers.

A text field is not the default choice for exact filtering, sorting, or aggregations. You should generally avoid enabling fielddata on text just to sort or aggregate; using a keyword subfield is more appropriate.

### Keyword: An Intact Single Value

A `keyword` field is indexed as a single term. The string:

~~~text
Wireless Mechanical Keyboard
~~~

is treated as one value rather than split into three tokens like a text field.

Keyword is well suited for:

- Exact matching with a `term` query.
- Filtering by status, category, brand, or SKU.
- Sorting.
- Terms aggregations.
- Grouping and cardinality.

Keyword is case-sensitive by default. If you want case-insensitive matching, you can use a normalizer or store an additional normalized field.

### Direct Comparison

| Characteristic | text | keyword |
|---|---|---|
| Token analysis | Yes | No, except a single-token normalizer |
| Full-text search | Suitable | Not the primary purpose |
| Exact term query | Usually unsuitable for the whole phrase | Suitable |
| Sort | Not recommended by default | Suitable |
| Aggregation | Usually not recommended by default | Suitable |
| Stemming | Configurable via analyzer | No |
| Lowercase | Via analyzer | Via normalizer if configured |
| Examples | name, description | sku, brand, status |

You should not treat `text` as "approximate search" and `keyword` as "strict exact search" in every case. The actual behavior depends on the analyzer, normalizer, query type, and specific mapping.

## 3. What Is Multi-Field?

Multi-field allows one source field to have multiple ways of being indexed. For example:

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

The document still only has:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch creates the indexed representations:

- `name`: text to analyze and search by words.
- `name.keyword`: keyword for exact match, sorting, and aggregations.

The name `name.keyword` is a field path in the mapping, not a nested JSON property in the source. The source does not need to contain:

~~~json
{
  "name": {
    "keyword": "Wireless Mechanical Keyboard"
  }
}
~~~

Multi-field does not create an independent source attribute. It creates additional representations in the index.

A field can have multiple subfields such as `name.keyword`, `name.folded`, or `name.english` if use cases require different semantics. Avoid creating subfields just because you can; every additional field increases indexing cost and must be maintained in the mapping.

## 4. Designing the Mapping for the Product Index

An explicit mapping helps control analyzers, exact matching, and sorting. The example below uses:

- `name`: text for searching.
- `name.keyword`: case-sensitive keyword for exact match.
- `name.folded`: lowercased and accent-folded keyword for a more user-friendly exact match.
- `description`: text.
- `sku`, `brand`, `category`, `status`: keyword.
- `priceMinor`: long to store price in the agreed smallest currency unit.

Creating the index:

~~~http
PUT /products-v1
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folding_lowercase": {
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
    "dynamic": "strict",
    "properties": {
      "productId": {
        "type": "keyword"
      },
      "sku": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          },
          "folded": {
            "type": "keyword",
            "normalizer": "folding_lowercase",
            "ignore_above": 256
          }
        }
      },
      "description": {
        "type": "text",
        "analyzer": "standard"
      },
      "brand": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "category": {
        "type": "keyword"
      },
      "tags": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "status": {
        "type": "keyword"
      },
      "priceMinor": {
        "type": "long"
      },
      "updatedAt": {
        "type": "date"
      }
    }
  }
}
~~~

`dynamic: strict` causes Elasticsearch to reject undeclared fields. This helps catch schema drift early, but every new field must be added to the mapping before writers send data.

Normalizers only apply to keyword fields and must produce a single token. `lowercase` and `asciifolding` ensure brand/name folded values are normalized at index time and when running matching term-level queries.

`ignore_above: 256` prevents overly long values from being indexed into the keyword subfield. The source can still retain the value, but exact match, sorting, and aggregations on that subfield will not work for documents exceeding the limit. Choose the threshold based on real data.

## 5. Choosing Meaningful Subfield Names

Subfield names should express their semantics:

| Field | Purpose |
|---|---|
| `name` | Full-text search |
| `name.keyword` | Case-sensitive exact match |
| `name.folded` | Exact match after lowercase/asciifolding |
| `description` | Full-text search |
| `brand` | Case-insensitive filter/grouping via normalizer |
| `sku` | Exact SKU, normalized according to policy |
| `category` | Exact category filter |
| `status` | Exact status filter |

Not every text field needs a keyword subfield. For example, a long description rarely needs exact-match or sorting. Conversely, `brand`, which is only used for filtering and aggregations, can be declared directly as keyword without a text parent.

Multi-field is most useful when **the same value** needs multiple indexing strategies. If your data has two distinct attributes such as `displayName` and `normalizedName` managed separately by business logic, represent them as two source properties rather than simulating a multi-field.

## 6. Mapping with Spring Data Elasticsearch

You can describe the document using annotations:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String productId;

    @Field(
            type = FieldType.Keyword,
            normalizer = "folding_lowercase"
    )
    private String sku;

    @MultiField(
            mainField = @Field(
                    type = FieldType.Text,
                    analyzer = "standard"
            ),
            otherFields = {
                    @InnerField(
                            suffix = "keyword",
                            type = FieldType.Keyword,
                            ignoreAbove = 256
                    ),
                    @InnerField(
                            suffix = "folded",
                            type = FieldType.Keyword,
                            normalizer = "folding_lowercase",
                            ignoreAbove = 256
                    )
            }
    )
    private String name;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String description;

    @Field(
            type = FieldType.Keyword,
            normalizer = "folding_lowercase"
    )
    private String brand;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(
            type = FieldType.Keyword,
            normalizer = "folding_lowercase"
    )
    private List<String> tags;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Long)
    private Long priceMinor;

    @Field(type = FieldType.Date)
    private Instant updatedAt;

    // Constructors, getters and setters
}
~~~

Key annotations:

- `@Field(type = FieldType.Text)` declares a full-text field.
- `@Field(type = FieldType.Keyword)` declares an exact/filter field.
- `@MultiField` declares the main field and its subfields.
- `@InnerField` defines a subfield with a suffix.
- `analyzer` controls tokenization for text.
- `normalizer` controls keyword normalization.
- `@Id` maps the document ID to `_id` metadata.

The annotations describe the mapping, but the custom normalizer `folding_lowercase` must still be declared in the index settings before the mapping uses it. You can manage settings with a JSON/YAML resource and create the index via `IndexOperations` or a dedicated migration/provisioning step.

Do not assume that simply having annotations on a class will automatically modify an existing production index. Index, mapping, and alias creation should follow a clear lifecycle.

## 7. Configuring Analyzers and Normalizers

The analyzer of a text field determines which tokens are indexed and queried. `standard` is suitable for much general English content, but it is not automatically the best analyzer for every language or every type of data.

For English, you might consider an analyzer with stop-word or stemming support:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "product_english": {
          "type": "standard",
          "stopwords": "_english_"
        }
      }
    }
  }
}
~~~

Then declare the text field to use that analyzer. If using a custom analyzer, ensure the analyzer is available on every node and the index is created with the right settings.

A normalizer is for keyword fields and does not split the value into multiple tokens. For example:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folding_lowercase": {
          "type": "custom",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  }
}
~~~

With this normalizer, `KEYWORKS` and `KeyWorks` are normalized to an equivalent form when indexing and searching that field. `asciifolding` also converts certain accented characters into their ASCII counterparts. This is a business choice: for brand names, it can be helpful; for SKUs where specific characters matter, you need to decide whether accents should be folded.

### Inspecting Analyzers with the _analyze API

~~~http
POST /products-v1/_analyze
{
  "analyzer": "standard",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Inspecting a normalizer/keyword field:

~~~http
POST /products-v1/_analyze
{
  "normalizer": "folding_lowercase",
  "text": "KeyWörks"
}
~~~

The output lets you see the actual tokens or normalized token. When search does not return expected results, checking the analyzer is usually faster than changing the query by guesswork.

## 8. Is Dynamic Mapping Enough?

Elasticsearch can automatically create mappings when it encounters new fields. For strings, dynamic mapping typically creates a text field with a `.keyword` subfield under the default configuration.

That is convenient for prototyping, but you should not rely solely on dynamic mapping for critical product indices because:

- The default analyzer may not suit the language.
- The keyword subfield may use a default `ignore_above`.
- Field names and data types are decided by the first document.
- Sending a number in the first document and a string in a later document can cause a mapping error.
- You lose control over normalizer, sorting, and aggregation semantics.
- An unexpected object can cause the mapping to grow uncontrollably.

Use explicit mappings for fields with well-defined roles: name, SKU, brand, category, status, price, and timestamps. Dynamic mapping can be enabled for controlled open-ended areas or disabled with `dynamic: strict` when the schema must remain strict.

## 9. Indexing Documents and Inspecting Fields

After creating the index, write a document:

~~~http
PUT /products-v1/_doc/P-1001
{
  "productId": "KB-1001",
  "sku": "KB-1001-BLK",
  "name": "Wireless Mechanical Keyboard",
  "description": "Compact keyboard with hot-swappable switches",
  "brand": "KeyWorks",
  "category": "ACCESSORIES",
  "tags": ["wireless", "mechanical", "keyboard"],
  "status": "PUBLISHED",
  "priceMinor": 1299000,
  "updatedAt": "2026-11-13T08:30:00Z"
}
~~~

Inspect the mapping:

~~~http
GET /products-v1/_mapping
~~~

Inspect the document source:

~~~http
GET /products-v1/_doc/P-1001
~~~

The returned source still has `name` as a string. Multi-fields only appear in the mapping/indexed representation, not as nested objects inside `_source`.

When using Spring Data to save:

~~~java
ProductDocument product = new ProductDocument();
product.setId("P-1001");
product.setProductId("KB-1001");
product.setSku("KB-1001-BLK");
product.setName("Wireless Mechanical Keyboard");
product.setDescription(
        "Compact keyboard with hot-swappable switches"
);
product.setBrand("KeyWorks");
product.setCategory("ACCESSORIES");
product.setStatus("PUBLISHED");
product.setPriceMinor(1_299_000L);
product.setUpdatedAt(Instant.now());

productRepository.save(product);
~~~

The Spring Data converter turns the object into the source document. The index mapping must be compatible with the actual fields and data types.

## 10. Full-Text Search with the match Query

`match` is the standard query for text fields. Elasticsearch analyzes the query value using the search analyzer configured for the field.

~~~http
GET /products-v1/_search
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

With the standard analyzer, the query text is split into the tokens `mechanical` and `keyboard`. Under the default operator, match uses OR semantics between tokens. You can require all tokens:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "mechanical keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

Or control the ratio of tokens that must match using `minimum_should_match`:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "wireless mechanical keyboard",
        "minimum_should_match": "2"
      }
    }
  }
}
~~~

Choose OR, AND, or a minimum percentage based on the search experience. AND is stricter but can exclude documents when users enter extra words that do not appear in the name.

## 11. Phrase Search with match_phrase

If words must appear in order and within an appropriate distance, use `match_phrase`:

~~~http
GET /products-v1/_search
{
  "query": {
    "match_phrase": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

`match_phrase` uses token positions to verify the phrase. It is not equivalent to exact string equality:

- Exact string equality: typically uses a keyword field.
- Phrase matching: uses a text field and match_phrase.
- Full-text matching: uses match/multi_match.

For example, the name `Wireless Mechanical Keyboard` can match the phrase `mechanical keyboard`, even though the source name is not equal to that string.

You can use `slop` to allow some token distance or transposition, but increasing slop broadens the query and can be more expensive. Add it only when the UX requires it.

## 12. Exact Match with the term Query

To find an exact SKU, use the keyword field and `term`:

~~~http
GET /products-v1/_search
{
  "query": {
    "term": {
      "sku": "KB-1001-BLK"
    }
  }
}
~~~

Case-sensitive exact name:

~~~http
GET /products-v1/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Exact name after lowercase/asciifolding normalization:

~~~http
GET /products-v1/_search
{
  "query": {
    "term": {
      "name.folded": "wireless mechanical keyboard"
    }
  }
}
~~~

With a keyword normalizer, eligible term-level queries are normalized according to the mapping. Verify with `_analyze` and integration tests for your exact server version.

Do not use `term` on the `name` text field expecting a whole-sentence match. A text field is analyzed into tokens; exact whole-value semantics belong to the keyword subfield.

## 13. Multi-Match Search Across Multiple Text Fields

A search screen often needs to search the same keywords across both name and description.

~~~http
GET /products-v1/_search
{
  "query": {
    "multi_match": {
      "query": "mechanical keyboard",
      "fields": [
        "name^3",
        "description"
      ],
      "type": "best_fields"
    }
  }
}
~~~

Meaning:

- `name^3`: increases the boost of the name field.
- `description`: supporting field.
- `best_fields`: picks the best-matching score across fields, optionally combined with a tie breaker depending on configuration.

Boost is not a probability. `^3` is simply a multiplier affecting the relevance score. Evaluate results with representative data rather than choosing a boost by intuition and treating it as a fixed rule.

Common multi_match types:

| Type | When to use |
|---|---|
| `best_fields` | One field matching well is enough, e.g., name or description |
| `most_fields` | Combine scores from multiple representations of the same content |
| `cross_fields` | Query words may be spread across multiple fields with compatible analyzers |
| `phrase` | Phrase search across multiple fields |
| `phrase_prefix` | Phrase with the last token treated as a prefix |

`most_fields` is useful when a single value is indexed with multiple analyzers, such as a main field and a stemmed subfield. `cross_fields` fits fields with compatible analyzers where query tokens may be distributed across them. Choose the type based on semantics instead of defaulting to one type for every search.

## 14. Combining Text Search with Exact SKU

When a user enters a string, you can prioritize an exact SKU match while still allowing full-text matching on name and description.

~~~http
GET /products-v1/_search
{
  "query": {
    "bool": {
      "should": [
        {
          "term": {
            "sku": {
              "value": "KB-1001-BLK",
              "boost": 10
            }
          }
        },
        {
          "term": {
            "name.keyword": {
              "value": "KB-1001-BLK",
              "boost": 8
            }
          }
        },
        {
          "multi_match": {
            "query": "KB-1001-BLK",
            "fields": [
              "name^3",
              "description"
            ],
            "type": "best_fields"
          }
        }
      ],
      "minimum_should_match": 1,
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

`should` provides alternative matching branches. `minimum_should_match: 1` requires at least one branch to match. The status and category filters restrict the document set without affecting the relevance score.

If the query text is not an SKU, the exact SKU clause will not match, while the full-text branches still work. In practice, you can detect the SKU format beforehand and build a different query, as long as that logic is an explicit business rule.

Never place security filters such as tenant scope inside `should`. Tenant and visibility constraints must always be placed in mandatory filters.

## 15. Using Spring Data NativeQuery

Modern Spring Data Elasticsearch provides `NativeQuery` to combine Elasticsearch Java API Client Query DSL with pagination and search options.

Multi-match example:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.multiMatch(mm -> mm
                .query("mechanical keyboard")
                .fields("name^3", "description")
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products-v1")
        );
~~~

`NativeQuery` is an Elasticsearch-specific query representation. If your project uses Spring Data Elasticsearch 4.x/HLRC, the query builder APIs and client differ; do not copy 5.x snippets directly into older projects without checking migration and API compatibility.

Reading each hit:

~~~java
hits.getSearchHits().forEach(hit -> {
    ProductDocument product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(hit.getScore());
});
~~~

`SearchHits<T>` retains metadata such as score, ID, sort values, highlight fields, and total hits. Extracting only the content into a list discards some of this metadata.

## 16. Building a Query Combining Filters and Multi-Match in Java

A production query typically performs full-text search while filtering by status, tenant, and category:

~~~java
String searchText = "mechanical keyboard";
String tenantId = "tenant-42";

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.multiMatch(mm -> mm
                        .query(searchText)
                        .fields("name^3", "description")
                ))
                .filter(f -> f.term(t -> t
                        .field("tenantId")
                        .value(tenantId)
                ))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value("PUBLISHED")
                ))
                .filter(f -> f.term(t -> t
                        .field("category")
                        .value("ACCESSORIES")
                ))
        ))
        .withPageable(PageRequest.of(0, 20))
        .build();
~~~

`must` holds the scored text query. `filter` holds mandatory conditions that do not require scoring.

If category is optional, add the filter only when the criteria contains a value. Tenant and visibility scopes must come from the authenticated identity and always be applied to regular user endpoints.

When there are multiple OR branches such as exact SKU or text match, place those branches inside a nested bool and explicitly set `minimum_should_match`.

## 17. Sorting by a Keyword Field

Sorting on a text field is usually inappropriate because text is tokenized and lacks doc values by default. Use the keyword subfield:

~~~http
GET /products-v1/_search
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    },
    {
      "productId": {
        "order": "asc"
      }
    }
  ],
  "query": {
    "match_all": {}
  }
}
~~~

`productId` acts as a tie-breaker to keep ordering stable when multiple products share the same name.

If you want case-insensitive and accent-insensitive sorting, you can use `name.folded`. Note that sorting by normalized values can yield a different lexicographical order than the original source.

Do not enable `fielddata=true` on a text field just to avoid creating a keyword subfield. Fielddata can consume significant heap memory. Design the mapping for sorting upfront.

## 18. Aggregations on Keyword Fields

Counting products by brand:

~~~http
GET /products-v1/_search
{
  "size": 0,
  "aggs": {
    "products_by_brand": {
      "terms": {
        "field": "brand",
        "size": 20
      }
    }
  }
}
~~~

A terms aggregation typically requires a keyword field or a field with suitable doc values. Using a `text` `brand` field can cause the aggregation to be rejected due to disabled fielddata or require enabling fielddata at a memory cost.

Counting by category:

~~~json
{
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

If an aggregation needs to display the original label while the keyword field is normalized, consider keeping both a display value field and a normalized key field, or using the bucket key to look up the display value in the application. Do not let normalization discard necessary display information.

## 19. Highlighting Text Search Results

Highlighting lets the UI mark matching text fragments:

~~~http
GET /products-v1/_search
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  },
  "highlight": {
    "fields": {
      "name": {},
      "description": {}
    }
  }
}
~~~

Highlighting operates on text fields and returns fragments. Do not assume fragments are always safe HTML to render; if using highlight tags, configure appropriate pre/post tags and escape content before rendering in the UI.

In Spring Data Elasticsearch, `SearchHit` can contain highlight fields. Map them to a response DTO rather than modifying the document source directly.

## 20. Searching by SKU and Prefix

SKU is usually a keyword because it requires exact semantics. If prefix matching is needed, you can use a prefix query:

~~~http
GET /products-v1/_search
{
  "query": {
    "prefix": {
      "sku": "KB-1001"
    }
  }
}
~~~

Prefix queries can be expensive if field cardinality is high or the prefix is too short. Enforce minimum input length limits, consider index design, and monitor latency.

If character-by-character autocomplete is needed, a prefix query on keyword is not always optimal. You can design an edge n-gram/search-as-you-type subfield or use a completion suggester depending on the UX. Analyzer and index settings must remain consistent between index analyzer and search analyzer.

Do not use wildcard queries like `*keyboard*` across fields as an autocomplete substitute; leading wildcards are usually expensive.

## 21. Analyzers for Vietnamese and Multilingual Content

The `standard` analyzer is a starting point, but it does not fully understand Vietnamese semantics, diacritics, word variations, and product-specific word segmentation.

Options depend on the data:

- Keep the original text and use an appropriate analyzer.
- Create an additional normalized field for exact matching/filtering.
- Use a language analysis plugin if advanced Vietnamese word segmentation is required.
- Use edge n-grams for autocomplete if required.
- Keep separate keyword fields for SKU, category, and brand codes.
- Test queries with accented/unaccented terms, punctuation, and special characters.

`asciifolding` handles certain accented-to-ASCII conversions, but it does not replace a Vietnamese tokenizer or grammar rules. Never assume lowercase + asciifolding provides the same Vietnamese search quality as a dedicated analyzer.

If you install an analysis plugin, it must be compatible with the Elasticsearch server version and present on all required nodes. Testcontainers must also include the same plugin so tests reflect the target environment.

## 22. Inspecting Mappings and Queries with _explain

When a document fails to match or scores unexpectedly, use `_explain`:

~~~http
GET /products-v1/_explain/P-1001
{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

The response explains whether the document matched and what contributed to its score.

Use `_validate/query` to check whether a query is valid:

~~~http
POST /products-v1/_validate/query?explain=true
{
  "query": {
    "multi_match": {
      "query": "mechanical keyboard",
      "fields": ["name^3", "description"]
    }
  }
}
~~~

Use `_analyze` to inspect tokens, `_mapping` to inspect field types, and `_explain` to understand scoring. Each API answers a different question.

## 23. Modifying Multi-Fields When an Index Already Has Data

You can add a multi-field to an existing mapping using put mapping if the change is supported:

~~~http
PUT /products-v1/_mapping
{
  "properties": {
    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    }
  }
}
~~~

However, there is a crucial point: **adding a multi-field does not automatically reindex values from existing documents into the new subfield**. Documents written after the change are indexed under the new mapping; older documents must be backfilled.

You can use `_update_by_query` to reprocess existing sources for the new field, or create a new versioned index and reindex. For example:

~~~http
POST /products-v1/_update_by_query
~~~

Run this in an appropriate environment, verify the updated document count, and monitor tasks and timeouts. For large indices, you may need batching, throttling, or a controlled reindex procedure.

You cannot arbitrarily change the type of an existing field—such as changing `name` from text to keyword—or change the analyzer of an existing field through an in-place mapping update. For incompatible changes, create a new index and reindex.

## 24. Versioned Indices and Aliases When Changing Mappings

A safer workflow for major mapping changes:

~~~text
products-v1
    |
    | Create products-v2 with new mapping
    v
Reindex documents from v1 to v2
    |
    v
Validate counts, mappings and representative searches
    |
    v
Switch read/write alias to v2
    |
    v
Monitor application
    |
    v
Retire v1 after rollback window
~~~

Example of switching an alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Aliases allow the application to use the stable name `products` while the physical index changes. Alias switching must be coordinated with writers and migrations to avoid unintended writes to the old or new index.

For mapping/analyzer changes, test reindexing, alias cutover, rollback, and data consistency. Do not delete the old index immediately after switching the alias.

## 25. Designing the Product Search API

The API request should express business intent:

~~~http
GET /api/products/search?q=mechanical%20keyboard&category=ACCESSORIES&page=0&size=20&sort=NAME_ASC
~~~

Request DTO:

~~~java
public record ProductSearchRequest(
        String q,
        String category,
        Integer page,
        Integer size,
        ProductSort sort
) {
}
~~~

A sort enum lets the server control allowed fields:

~~~java
public enum ProductSort {
    RELEVANCE,
    NAME_ASC,
    PRICE_ASC,
    UPDATED_DESC
}
~~~

Service:

~~~java
@Service
public class ProductSearchService {

    private final ProductSearchRepository searchRepository;
    private final CurrentTenantProvider tenantProvider;

    public ProductSearchResponse search(ProductSearchRequest request) {
        String tenantId = tenantProvider.requiredTenantId();

        ProductSearchCriteria criteria = new ProductSearchCriteria(
                tenantId,
                request.q(),
                request.category(),
                normalizePage(request.page()),
                normalizeSize(request.size()),
                normalizeSort(request.sort())
        );

        return searchRepository.search(criteria);
    }
}
~~~

In a real service, inject the repository and provider via constructor; the example above focuses on the flow. Never take a tenant ID from a query parameter without authorization checks.

Page size needs a default and a maximum. Sort fields need an allowlist. If the query is empty, decide whether the endpoint allows browsing all products within the tenant or requires at least one condition.

## 26. Repository Search Adapter

A custom search adapter can use `ElasticsearchOperations` to run a NativeQuery:

~~~java
public interface ProductSearchRepository {

    ProductSearchResult search(ProductSearchCriteria criteria);
}
~~~

~~~java
@Repository
public class ProductSearchRepositoryImpl
        implements ProductSearchRepository {

    private final ElasticsearchOperations operations;
    private final ProductSearchQueryBuilder queryBuilder;

    public ProductSearchRepositoryImpl(
            ElasticsearchOperations operations,
            ProductSearchQueryBuilder queryBuilder
    ) {
        this.operations = operations;
        this.queryBuilder = queryBuilder;
    }

    @Override
    public ProductSearchResult search(ProductSearchCriteria criteria) {
        NativeQuery query = queryBuilder.build(criteria);

        SearchHits<ProductDocument> hits = operations.search(
                query,
                ProductDocument.class,
                IndexCoordinates.of("products")
        );

        return ProductSearchResult.from(hits);
    }
}
~~~

This keeps controllers and services decoupled from Query DSL. For very simple queries, derived repository methods remain suitable. Use a custom fragment when you need multi-match, exact SKU boosting, optional filters, highlighting, or aggregations.

## 27. Result DTOs and Relevance Score

Search responses often need both document data and metadata:

~~~java
public record ProductSearchItem(
        String productId,
        String name,
        String brand,
        Long priceMinor,
        Float score
) {
}
~~~

~~~java
public record ProductSearchResponse(
        List<ProductSearchItem> items,
        long totalHits,
        int page,
        int size
) {
}
~~~

Mapping from `SearchHit<ProductDocument>`:

~~~java
private ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
    ProductDocument source = hit.getContent();

    return new ProductSearchItem(
            source.getProductId(),
            source.getName(),
            source.getBrand(),
            source.getPriceMinor(),
            hit.getScore()
    );
}
~~~

You do not necessarily need to expose the score in a public API. You can use the score for internal ranking and return only the order. If the response needs highlights, add a separate field containing safely processed fragments.

Never return the persistence entity directly if it contains tenant IDs, internal notes, or indexing-only fields.

## 28. Testcontainers Integration Tests

Unit tests can verify that the query builder emits the right field names, boosts, and bool structure. However, only integration tests against a real Elasticsearch instance verify mappings, analyzers, normalizers, and query behavior.

A container test should pin its version:

~~~java
@Testcontainers
@SpringBootTest
class ProductSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.x.y"
            );

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add(
                "spring.elasticsearch.uris",
                elasticsearch::getHttpHostAddress
        );
    }
}
~~~

`8.x.y` is a placeholder. Use an image compatible with your Spring Data/client versions and pin the same version as your target server.

Test cases to cover:

1. `match(name)` finds tokens in the name.
2. `match(description)` finds tokens in the description.
3. `term(sku)` matches the exact SKU.
4. `term(name.keyword)` behaves case-sensitively per mapping.
5. `term(name.folded)` handles case/diacritics per normalizer.
6. Sorting by `name.keyword` works.
7. Aggregating by `brand` works.
8. `multi_match` prioritizes name according to the boost.
9. Documents with missing fields or keyword values exceeding `ignore_above` are handled as designed.
10. Tenant filtering never returns documents from another tenant.

## 29. Testing Analyzers and Scoring

Do not assert only that documents are present in the results. Verify the ordering when scoring is a UX requirement.

Example dataset:

| ID | Name | Description |
|---|---|---|
| P1 | Mechanical Keyboard | Compact wireless keyboard |
| P2 | Wireless Mouse | Mechanical switches not included |
| P3 | Keyboard Stand | Stand for mechanical keyboard |

For the query `mechanical keyboard`, you may expect P1 to rank higher because its name matches both tokens and is boosted. P3 may also match; P2 matches only via description depending on query semantics.

Test actual queries and inspect `_explain` if the ordering is wrong. Relevance depends on corpus, analyzers, field length, term frequency, boosts, and query types; avoid asserting an exact numeric score unless you control every document and index setting.

Also verify:

- Accented and unaccented words.
- Uppercase and lowercase.
- Hyphens in SKUs.
- Single words and phrases.
- Stop-word tokens.
- Long names exceeding ignore_above.
- Brands with multiple casing variants.
- New documents and backfilled documents.

## 30. Common Pitfalls

### Using text for Every Field

Filtering, sorting, and aggregating on text is either unsuitable or requires heap-heavy fielddata. Use keyword for status, SKU, category, and brand.

### Using keyword for Product Names and Expecting Word Search

Keyword preserves the entire value intact. Use a text field for full-text search.

### Using a term Query on text

Text has been analyzed into tokens. Exact whole-value matching should use a keyword subfield.

### Using a match Query on SKU

SKUs usually require exact semantics. Use keyword and term queries; prefix/autocomplete is a separate use case.

### Assuming Multi-Field Creates Extra Source Attributes

Multi-field creates indexed representations, not nested JSON objects in the source.

### Assuming Adding a Multi-Field Automatically Backfills Existing Documents

Old documents must be reprocessed via update_by_query or reindex to populate the new subfield.

### Sorting on a text Field

Use a keyword subfield with doc values. Avoid enabling fielddata solely for sorting.

### Aggregating on a text Field

Use a keyword field/subfield for terms aggregations.

### Expecting Case-Insensitive Exact Match Without a Normalizer

Keyword fields are case-sensitive by default. Declare a normalizer or normalized field as needed.

### Treating asciifolding as a Complete Vietnamese Analyzer

Asciifolding only transforms certain characters. Vietnamese search with advanced word-segmentation or semantic requirements needs an appropriate analyzer/plugin and real testing.

### Changing Analyzers or Field Types Directly on an Existing Index

Incompatible changes usually require a new index and reindexing. Do not attempt to mutate them in place.

### Relying on Dynamic Mapping for Product Schemas

The first document determines the mapping and can produce an unsuitable schema. Declare explicit mappings for key fields.

### Unit Testing Only the Query Builder

Unit tests do not validate analyzers, mappings, or server behavior. Add integration tests.

## 31. Implementation Workflow

When building product search with text, keyword, and multi-field:

1. List use cases: full-text, exact SKU, exact name, filtering, sorting, aggregations, and autocomplete.
2. Choose `text` for content requiring tokenization.
3. Choose `keyword` for exact/filter/sort/aggregation values.
4. Use `@MultiField` or explicit mappings to create representations of the same source value.
5. Declare analyzers and normalizers before creating mappings that use them.
6. Choose normalizers based on semantics; do not automatically lowercase/asciifold every identifier.
7. Create the index with an explicit mapping and verify with `_mapping`.
8. Inspect tokens with `_analyze`.
9. Use `match`, `match_phrase`, and `multi_match` for full-text search.
10. Use `term` on keyword fields for exact matches.
11. Combine relevance clauses with mandatory filters such as tenant/status.
12. Use keyword subfields for sorting and aggregations.
13. Map SearchHits to response DTOs.
14. If adding a multi-field, backfill existing documents; if changing types/analyzers, create a new index and reindex.
15. Test against a pinned Elasticsearch version with representative data.
16. Monitor search latency, hit quality, shard behavior, and index size.

## References

- [Elasticsearch — Text field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/text.html)
- [Elasticsearch — Keyword field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/keyword.html)
- [Elasticsearch — Multi-fields](https://www.elastic.co/guide/en/elasticsearch/reference/current/multi-fields.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Analyzers](https://www.elastic.co/guide/en/elasticsearch/reference/current/analysis-analyzers.html)
- [Elasticsearch — Normalizers](https://www.elastic.co/guide/en/elasticsearch/reference/current/normalizer.html)
- [Elasticsearch — Match query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-match-query.html)
- [Elasticsearch — Match phrase query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-match-query-phrase.html)
- [Elasticsearch — Multi-match query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-multi-match-query.html)
- [Elasticsearch — Term query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-term-query.html)
- [Elasticsearch — Update by query](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update-by-query.html)
- [Spring Data Elasticsearch — Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

## Conclusion

Build product search properly by using `text` for analyzed content and `keyword` for exact matching, filtering, sorting, and aggregations. Multi-field lets the same source value have multiple indexed representations such as `name`, `name.keyword`, and `name.folded`. In Spring Data Elasticsearch, declare mappings via annotations or managed index settings/mappings; use match/multi_match for full-text and term for keyword. When updating mappings, remember that a new multi-field does not automatically backfill existing data; verify analyzers, mappings, sorting, aggregations, and scoring with integration tests on a real Elasticsearch cluster before deployment.
