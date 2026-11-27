# Normalizers for Keywords and Case-Insensitive Search

In Elasticsearch, `keyword` fields are commonly used to store values requiring exact matching such as usernames, emails, product codes, statuses, or group names. However, exact matching is case-sensitive by default. For example, `Alice`, `ALICE`, and `alice` are treated as distinct values.

A **normalizer** lets you normalize the value of a `keyword` field before Elasticsearch indexes it and when processing search values. This allows an application to perform case-insensitive searches while preserving the semantics of a keyword value: the entire string is treated as a single value rather than being split into multiple tokens like a `text` field.

This article focuses on normalizers—especially the `lowercase` and `asciifolding` filters—how to declare mappings, how to query, and how to integrate with Spring Data Elasticsearch.

## 1. Distinguishing `keyword`, `text`, and `normalizer`

Two common field types are `keyword` and `text`:

| Characteristic | `keyword` | `text` |
|---|---|---|
| Purpose | Whole values, exact filtering, sorting, aggregations | Text content requiring full-text search |
| Tokenization | Does not use an analyzer to split words | Has an analyzer to analyze content |
| Examples | Email, order code, status | Product description, article body |
| Common queries | `term`, `terms`, `range` depending on field type | `match`, `match_phrase` |
| Normalization | Can use a normalizer | Uses an analyzer |

Suppose a document contains:

```json
{
  "username": "Alice Nguyen",
  "description": "Java Developer"
}
```

If `username` is `keyword`, Elasticsearch treats the entire `Alice Nguyen` as one value. A `term` query looks for the intact value without splitting it into `Alice` and `Nguyen`.

If `description` is `text`, the analyzer may split the content into tokens such as `java` and `developer`, depending on the configured analyzer.

A normalizer is a normalization mechanism for `keyword` fields. It does not turn a keyword into text, nor does it perform linguistic analysis or split sentences into words. Typically, a normalizer must produce exactly one token from the input.

## 2. Case-sensitivity issues when searching keywords

Suppose an index has the documents:

```json
{ "username": "Alice" }
{ "username": "BOB" }
{ "username": "charlie" }
```

Simple mapping:

```json
{
  "properties": {
    "username": {
      "type": "keyword"
    }
  }
}
```

Query:

```http
GET /users/_search
{
  "query": {
    "term": {
      "username": "alice"
    }
  }
}
```

does not find the document with `username = "Alice"`, because keywords by default are matched against the indexed value and are case-sensitive.

One approach is to normalize both the indexed value and the query value to the same form. For example, converting all letters to lowercase:

```text
Alice  -> alice
ALICE  -> alice
alice  -> alice
```

A normalizer handles this consistently, rather than requiring every place in the application to call `toLowerCase()`.

## 3. How does a normalizer work?

A normalizer is an analysis configuration dedicated to keywords. A custom normalizer can combine:

- Character filters: transform characters before the token filter step.
- Token filters: transform the single token of the keyword value.

A normalizer does not declare its own tokenizer like an analyzer. It uses keyword tokenization mechanics and only permits filters suitable for a single token. Filters that generate multiple tokens or split text into multiple parts are not valid for a normalizer.

Two commonly used token filters:

- `lowercase`: converts letters to lowercase.
- `asciifolding`: converts many accented Unicode characters or non-ASCII characters to close ASCII equivalents.

Example custom normalizer:

```json
{
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
```

Illustrative results:

| Input value | After `lowercase` | After `asciifolding` |
|---|---|---|
| `Alice` | `alice` | `alice` |
| `ALICE` | `alice` | `alice` |
| `Café` | `café` | `cafe` |
| `Đặng` | `đặng` | `dang` |
| `MÜNCHEN` | `münchen` | `munchen` |

Exact output depends on the conversion table of the ASCII folding filter. It is not a complete linguistic transliteration rule. For Vietnamese or other languages, test the accented cases and special characters your business logic needs to support.

### 3.1. Use only `lowercase` or add `asciifolding`?

If the requirement is solely case-insensitivity, a normalizer with `lowercase` is sufficient:

```json
{
  "analysis": {
    "normalizer": {
      "lowercase_normalizer": {
        "type": "custom",
        "filter": ["lowercase"]
      }
    }
  }
}
```

In that case:

- `ALICE` and `Alice` are normalized to `alice`.
- `Café` and `café` are normalized to `café`.
- `cafe` still differs from `café`.

If you also want to strip accents for characters supported by ASCII folding, add `asciifolding`:

```json
{
  "analysis": {
    "normalizer": {
      "folding_lowercase": {
        "type": "custom",
        "filter": ["lowercase", "asciifolding"]
      }
    }
  }
}
```

Then `Café`, `CAFÉ`, and `cafe` can all be normalized to the same value `cafe`.

Which approach to choose depends on data semantics. If diacritics carry distinguishing meaning in identifiers, account names, or legal data, do not automatically strip accents just to make search more lenient.

## 4. Declaring a normalizer when creating an index

The normalizer must be defined in index settings and attached to a `keyword` field via the mapping.

Example index creation:

```http
PUT /users
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
    "properties": {
      "username": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      },
      "email": {
        "type": "keyword",
        "normalizer": "lowercase"
      },
      "displayName": {
        "type": "keyword",
        "normalizer": "folding_lowercase"
      }
    }
  }
}
```

In this example:

- `folding_lowercase` is a custom normalizer defined by the index.
- `username` and `displayName` use lowercasing combined with ASCII folding.
- `email` uses the built-in `lowercase` normalizer.
- Fields without a declared normalizer retain default keyword behavior.

Elasticsearch provides the built-in `lowercase` normalizer. If you only need lowercasing, you can reference this name directly without defining a custom normalizer.

After creating the index, check the mapping:

```http
GET /users/_mapping?pretty
```

And check the settings:

```http
GET /users/_settings?pretty
```

When creating an index from an application, ensure settings defining the normalizer are applied before the field mapping references that normalizer name. If the index already exists with an old mapping, do not assume changing annotations in Java will automatically update the existing mapping.

## 5. Case-insensitive querying

Once a field has a normalizer attached, Elasticsearch normalizes keyword values when indexing and when processing search values for that field.

Example:

```http
GET /users/_search
{
  "query": {
    "term": {
      "username": "ALICE"
    }
  }
}
```

If a document stored `username = "Alice"`, a query with `ALICE` can still match because both are normalized to the same value.

Similarly:

```http
GET /users/_search
{
  "query": {
    "term": {
      "displayName": "CAFÉ"
    }
  }
}
```

With the `folding_lowercase` normalizer, the query value is normalized to `cafe`, so it can match documents containing `Café`, `CAFÉ`, or `cafe`.

### 5.1. Why does the `term` query still work?

A `term` query matches the exact value of a field. "Exact" here means exact against the normalized and indexed value, not necessarily the original character string.

This is different from changing `term` to `match`. A normalizer does not turn a keyword field into a text field. You are still searching for an intact value.

For a `keyword` field without a normalizer, `term` is case-sensitive against the indexed value. For a `keyword` field with a normalizer, both the indexed value and the query value pass through the same normalization rules.

### 5.2. Does not modify `_source` content

A normalizer changes the term form that Elasticsearch indexes and uses for searching. It does not overwrite the original string in `_source`.

Example document submitted:

```json
{
  "username": "Alice"
}
```

When retrieving the document:

```http
GET /users/_doc/1
```

`_source.username` can still be `Alice`. However, the term used for searching, sorting, or aggregations on the normalized field can be `alice`.

This allows the application to preserve the original spelling for display while supporting case-insensitive search.

## 6. Testing a normalizer with the Analyze API

Before putting a mapping into production, you can inspect normalization results using the Analyze API.

Example testing the normalizer attached to the `username` field:

```http
POST /users/_analyze
{
  "field": "username",
  "text": "ÁLICE"
}
```

The abbreviated response can contain the token:

```json
{
  "tokens": [
    {
      "token": "alice",
      "start_offset": 0,
      "end_offset": 5,
      "type": "word",
      "position": 0
    }
  ]
}
```

With a custom normalizer combining `lowercase` and `asciifolding`, the value `ÁLICE` is converted into `alice`.

You can test additional cases:

```http
POST /users/_analyze
{
  "field": "username",
  "text": [
    "Alice",
    "ALICE",
    "Café",
    "CAFÉ",
    "cafe",
    "Đặng"
  ]
}
```

The Analyze API lets you see the normalized output before concluding a query is wrong. If the field does not exist or the mapping does not yet have the normalizer attached, the result may differ from expectations.

Test real business data as well: accented characters, hyphens, dots, whitespace, emails, digits, Unicode characters, and language-specific edge cases.

## 7. Combining normalizers with multi-fields

Sometimes a single field needs two query modes:

- Full-text search across content.
- Exact matching that is case-insensitive.

Multi-fields allow a single value to be indexed under multiple field types. Example:

```http
PUT /products
{
  "settings": {
    "analysis": {
      "normalizer": {
        "folding_lowercase": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "folded": {
            "type": "keyword",
            "normalizer": "folding_lowercase"
          }
        }
      }
    }
  }
}
```

With this mapping:

- `name` is a `text` field serving full-text search.
- `name.folded` is a normalized `keyword` field for exact matching, sorting, or aggregations.

Full-text search:

```http
GET /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
```

Searching for the intact value without case or accent sensitivity according to the normalizer:

```http
GET /products/_search
{
  "query": {
    "term": {
      "name.folded": "WIRELESS MOUSE"
    }
  }
}
```

This is a useful pattern when the same property needs both content search and exact filtering. Give the subfield a clear name—such as `folded`, `normalized`, or `raw_ci`—so query authors understand its semantics.

## 8. Normalizers for sorting and aggregations

Normalizers are also useful when you need to group values with different casing into the same bucket or sort based on normalized values.

Example aggregation:

```http
GET /users/_search
{
  "size": 0,
  "aggs": {
    "usernames": {
      "terms": {
        "field": "username"
      }
    }
  }
}
```

If the `username` field uses a lowercase normalizer, documents with `Alice`, `ALICE`, and `alice` can be grouped into the same bucket by the normalized term.

Sorting also relies on the indexed keyword value:

```http
GET /users/_search
{
  "query": {
    "match_all": {}
  },
  "sort": [
    {
      "username": {
        "order": "asc"
      }
    }
  ]
}
```

If you need to preserve both the original spelling and normalized sorting, you can use multi-fields or a separate subfield. Keep in mind that aggregations on a normalized field will display the normalized key, not the original spelling in `_source`.

## 9. Integrating normalizers in Spring Data Elasticsearch

Spring Data Elasticsearch provides annotations to describe field mappings. In versions supporting the `normalizer` attribute on `@Field`, an entity can declare:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "users")
@Setting(settingPath = "/elasticsearch/users-settings.json")
public class User {

    @Id
    private String id;

    @Field(type = FieldType.Keyword, normalizer = "folding_lowercase")
    private String username;

    @Field(type = FieldType.Keyword, normalizer = "lowercase")
    private String email;

    // constructors, getters and setters
}
```

The settings file is placed on the classpath, for example `src/main/resources/elasticsearch/users-settings.json`:

```json
{
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
```

Here:

- `@Setting` references the settings file for Spring Data to use when creating the index.
- `@Document` declares the entity's index name.
- `@Field(type = FieldType.Keyword, normalizer = ...)` attaches the normalizer defined in settings to the field.
- `username` uses the custom normalizer; `email` uses the built-in `lowercase` normalizer.

Package names and annotation capabilities depend on the Spring Data Elasticsearch version. If your project uses a version without the `normalizer` attribute or a different way of declaring settings, check the exact API for your current dependency. The key requirement is that settings creating the normalizer and the field mapping must be applied together when the index is created.

### 9.1. Using `IndexOperations` to inspect an index

You can inspect the index and mapping via `ElasticsearchOperations`:

```java
IndexOperations indexOps = operations.indexOps(User.class);

boolean exists = indexOps.exists();

if (exists) {
    Map<String, Object> mapping = indexOps.getMapping();
    Map<String, Object> settings = indexOps.getSettings();
}
```

This snippet illustrates reading live metadata from Elasticsearch. When debugging, verify:

- The index actually exists.
- Settings contain the normalizer with the exact expected name.
- The field mapping references the right normalizer.
- The application is connected to the right cluster and the right index.
- The repository or `ElasticsearchOperations` uses the intended entity/mapping.

Changing annotations in source code does not prove the existing index has been updated. If the index already existed beforehand, read the mapping and settings directly from Elasticsearch.

## 10. Changing a normalizer when an index already exists

A normalizer is part of how a field is indexed. You cannot arbitrarily change the normalizer of an existing field like changing an ordinary configuration value.

If the `username` field was created without a normalizer and later you want to switch to `lowercase`, the safe approach is usually:

1. Create a new index with settings containing the normalizer.
2. Create the field mapping referencing that normalizer.
3. Reindex data from the old index to the new index.
4. Verify document count, mapping, and query results.
5. Switch the alias or application to the new index after confirming the data is correct.

Example creating the new index:

```http
PUT /users-v2
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
      "username": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
```

Then reindex:

```http
POST /_reindex
{
  "source": {
    "index": "users"
  },
  "dest": {
    "index": "users-v2"
  }
}
```

Reindexing writes data to the destination index and can be resource-intensive for large datasets. Follow a migration procedure and verify mappings and data after copying. If the application is writing concurrently to the old index, plan how to sync changes occurring during migration before switching the alias.

Another option is adding a multi-field to the existing mapping in cases supported by Elasticsearch, then updating/reindexing old documents so the subfield gets indexed. Merely adding a mapping does not regenerate previously indexed data. For analysis or normalizer changes, creating a new index usually makes the process easier to control.

## 11. Comparing normalizers with other case-insensitive search approaches

| Approach | Scope | Pros | Limitations |
|---|---|---|---|
| Keyword without normalizer | Case-sensitive keyword matching | Preserves original semantics | `Alice` differs from `alice` |
| Keyword + lowercase normalizer | Whole-value, case-insensitive matching | Consistent at index and query time; supports sort/aggregation | Must configure mapping upfront |
| Keyword + lowercase + asciifolding | Whole-value matching, ignoring case and some accents | Useful for data needing approximate accent matching | Can merge business values that are inherently distinct |
| Text + analyzer | Full-text search | Supports tokenization, stemming, and analysis steps | Not whole-value exact matching like keyword |
| Term query with `case_insensitive` | Case-insensitive ASCII matching on supported versions | Can be used for some queries without changing mapping | Limited scope; does not replace accent normalization or normalizer semantics |

Some Elasticsearch versions support the `case_insensitive` option on `term` queries. This capability depends on the version and supported character sets; the API documentation specifies its exact scope. If you need consistent normalization rules for searching, sorting, and aggregations, a normalizer is usually the clearer choice.

## 12. Cases requiring careful consideration

### 12.1. Not every field should be case-insensitive

Values like usernames or emails often have case-insensitive matching requirements at the application layer. However, identifiers, tokens, passwords, case-sensitive codes, or data needing exact semantics may not be appropriate for a lowercase normalizer.

Do not apply a single normalizer to every field just to simplify queries. Matching rules must derive from the business meaning of the data.

### 12.2. ASCII folding can collapse multiple values into one

If using both `lowercase` and `asciifolding`, values like `cafe` and `café` can both become `cafe`. This is helpful for user-friendly search, but can cause logical collisions when two values need to remain distinct.

If you need both capabilities, store the original value and create a normalized subfield for search. Do not use the normalized value as a unique key if business rules require distinguishing original forms.

### 12.3. Language-specific casing rules

Lowercasing is not always straightforward across all languages. Some languages have specialized upper/lowercase conversion rules. For multilingual data, inspect Unicode cases and required locale rules; do not assume a default lowercasing step resolves every language rule.

### 12.4. Do not confuse a normalizer with an analyzer

A normalizer does not split content into multiple words. If you need to search parts of a name, search phrases, or run full-text search, use a `text` field with an appropriate analyzer. If you need case-insensitive whole-value matching, use a `keyword` field with a normalizer.

You can combine both using multi-fields to serve both needs from the same source value.

## 13. Troubleshooting checklist when case-insensitive queries fail

When a query still returns no results, check in order:

**Step 1 — Verify the field mapping**

```http
GET /users/_mapping?pretty
```

Check whether the field has type `keyword` and a `normalizer` attribute with the exact expected name.

**Step 2 — Verify settings**

```http
GET /users/_settings?pretty
```

Check that the normalizer is declared in analysis settings and the referenced name matches the mapping.

**Step 3 — Verify normalization output**

```http
POST /users/_analyze
{
  "field": "username",
  "text": "ÁLICE"
}
```

Check whether the generated token matches business expectations.

**Step 4 — Check original documents**

```http
GET /users/_search
{
  "query": {
    "match_all": {}
  },
  "size": 5
}
```

Confirm documents were written to the right index and `_source` has the expected value.

**Step 5 — Run the `term` query directly**

```http
GET /users/_search
{
  "query": {
    "term": {
      "username": "ALICE"
    }
  }
}
```

If the query on a normalized keyword field still fails to match, confirm the document was indexed after the mapping had the normalizer, the query targets the right index/alias, and the field name is exact.

**Step 6 — Check legacy data**

If the normalizer was only added to the mapping or a new index, but old documents have not been reindexed/updated, existing data may lack terms under the new rules. Check index creation history and migration progress.

## 14. Quick reference table

| Requirement | Configuration or query |
|---|---|
| Case-insensitive only | Keyword with `lowercase` normalizer |
| Case-insensitive and strip some accents | Custom normalizer with `lowercase` and `asciifolding` |
| Whole-value matching | `term` query on `keyword` field |
| Full-text search | `match` query on `text` field |
| Check normalization output | Analyze API with `field` parameter |
| Sort/aggregate by normalized value | Use `keyword` field with normalizer |
| Both full-text and exact normalized | Multi-fields: `text` and `keyword` |
| Change normalizer for existing data | Create new index and reindex according to plan |

A normalizer normalizes keyword values using the same rule at both index time and search time. For case-insensitive needs, `lowercase` is usually enough; if accent removal is needed, `asciifolding` can be added after assessing the risk of collapsing distinct values. In Spring Data Elasticsearch, settings define the normalizer and entity mappings reference its name. Always inspect the live mapping, test with the Analyze API, and manage migrations when changing existing indices.
