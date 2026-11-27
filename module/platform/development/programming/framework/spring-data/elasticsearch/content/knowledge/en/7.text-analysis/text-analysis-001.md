# Distinguishing Index-Time and Search-Time Analysis

Elasticsearch uses an **analyzer** to convert text into tokens for search. This process happens at two different times:

- **Index-time analysis**: analyzing content when a document is written to the index.
- **Search-time analysis**: analyzing query text when a user performs a search.

The two processes are closely related but do not necessarily have to use the same analyzer. Understanding the difference clearly helps with designing mappings, choosing analyzers, and handling scenarios such as casing, stemming, stop words, and synonyms.

## 1. Two analysis stages in the search flow

When a document is indexed, Elasticsearch analyzes the value of a `text` field and stores the tokens in the inverted index. When receiving a full-text query, Elasticsearch can analyze the query text and then look up the corresponding tokens in the inverted index.

~~~mermaid
flowchart TD
    A["Document JSON"] --> B["Index-time analyzer"]
    B --> C["Tokens"]
    C --> D["Inverted index"]
    E["Search text"] --> F["Search-time analyzer"]
    F --> G["Query tokens"]
    G --> H["Match against inverted index"]
    D --> H
    H --> I["Search results and relevance score"]
~~~

For example, a document has the content:

`The Quick Brown Foxes`

The index-time analyzer may convert the content into:

`quick`, `brown`, `fox`

When a user searches for:

`QUICK FOX`

The search analyzer may convert the query into:

`quick`, `fox`

The two token sets are compatible, so Elasticsearch can find the document.

The core point is that **tokens produced at index time must be compatible with tokens produced by the query**. If the two analyzers process the same word in incompatible ways, search results may miss documents or fail to match even when the original content looks similar.

## 2. What components make up an analyzer?

An analyzer typically consists of three stages:

1. **Character filters**: preprocess the input string before tokenization, such as removing or replacing certain characters.
2. **Tokenizer**: splits the string into tokens according to rules, such as splitting on word boundaries.
3. **Token filters**: transform tokens, such as lowercasing, removing stop words, stemming, or adding synonyms.

For example, the `standard` analyzer typically splits text into tokens and converts them to lowercase. The `english` analyzer can perform additional English-language processing such as removing stop words and stemming.

The same analyzer can be used at both index time and search time. However, when the application has specific requirements for queries, you can declare different analyzers for the two stages.

## 3. Index-time analysis

Index-time analysis occurs when Elasticsearch receives a document to index. The analyzer is declared using the field's `analyzer` mapping parameter.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "english"
      }
    }
  }
}
~~~

When a document is indexed:

~~~json
{
  "description": "The applications are running quickly"
}
~~~

The `english` analyzer processes the content using English rules. Depending on the analyzer configuration, tokens may be lowercased, stripped of stop words, and reduced to their root form via stemming.

Index-time analysis has the following characteristics:

- Occurs when a document is indexed or reindexed.
- Determines the tokens written into the inverted index.
- Changing the index analyzer does not automatically re-analyze existing documents.
- Affects how data is found in subsequent queries.

Therefore, choosing the index analyzer is an important decision when designing a mapping. If you change tokenization or stemming rules after data already exists, you usually need to create a new index and reindex the data.

## 4. Search-time analysis

Search-time analysis occurs when Elasticsearch processes a full-text query. The `search_analyzer` mapping parameter lets you declare the analyzer used when analyzing query text.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "english",
        "search_analyzer": "standard"
      }
    }
  }
}
~~~

In this example:

- `analyzer: english` is used to analyze content when indexing documents.
- `search_analyzer: standard` is used to analyze query text.

When a user searches with `match`:

~~~json
{
  "query": {
    "match": {
      "description": "RUNNING applications"
    }
  }
}
~~~

Elasticsearch uses the search analyzer configured for the field to analyze the query string before looking up tokens in the inverted index.

### Why is a separate search analyzer needed?

There are several cases where an application wants to process query text differently from document content:

- Expanding synonyms at search time.
- Normalizing queries with custom rules.
- Keeping indexing stable while tuning the search experience.
- Applying different analysis rules for regular queries and phrase queries.

A search analyzer does not rewrite tokens already stored in the inverted index. It only determines how query text is converted into tokens to match against indexed data.

## 5. When `search_analyzer` is not declared

If a field declares `analyzer` but does not declare `search_analyzer`, the index-time analyzer is typically also used as the search analyzer for that field.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard"
      }
    }
  }
}
~~~

In this case, `standard` is used at index time and by default when analyzing queries as well.

If no specific analyzer is declared, Elasticsearch uses the default analyzer according to the index configuration, usually `standard`.

Do not assume every field automatically has its own analyzer. For `keyword` fields, Elasticsearch does not split strings into tokens like `text` fields; if you need to normalize keyword values, use a normalizer.

## 6. Distinguishing `analyzer`, `search_analyzer`, and `search_quote_analyzer`

These three mapping parameters serve different roles:

| Parameter | When used | Purpose |
|---|---|---|
| `analyzer` | Index time | Analyzes field content when indexing |
| `search_analyzer` | Search time | Analyzes regular query text |
| `search_quote_analyzer` | Search time | Analyzes text enclosed in quotation marks in a `query_string` query |

`search_quote_analyzer` is useful when you want to process quoted text in a `query_string` query with separate rules, such as not expanding synonyms for that phrase. If omitted, Elasticsearch defaults to `search_analyzer`.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "analyzer": "content_index",
        "search_analyzer": "content_search",
        "search_quote_analyzer": "content_phrase_search"
      }
    }
  }
}
~~~

The analyzers `content_index`, `content_search`, and `content_phrase_search` must be defined in the index settings before the mapping references them. `content_phrase_search` will be used for quoted text in `query_string` according to this mapping.

Not every query uses the search analyzer in the same way. `match` and `match_phrase` are full-text queries that analyze input. Term-level queries such as `term` match existing terms and do not analyze the input string like `match`.

## 7. Example: using separate analyzers for index and search

Suppose an application searches product names. At index time, we want lowercasing and English stemming. At search time, in addition to those steps, we want to expand certain synonyms such as `tv` and `television`.

Settings can be defined as follows:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        },
        "product_synonyms": {
          "type": "synonym_graph",
          "synonyms": [
            "tv, television",
            "laptop, notebook"
          ]
        }
      },
      "analyzer": {
        "product_index": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stemmer"
          ]
        },
        "product_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stemmer",
            "product_synonyms"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "product_index",
        "search_analyzer": "product_search"
      }
    }
  }
}
~~~

In this example:

- `product_index` is used when storing product names.
- `product_search` is used when analyzing user-entered keywords.
- `product_synonyms` is a synonym graph filter applied at search time.
- `name` remains a single text field; the application does not need to create two separate Java properties.

In the example, `english_stemmer` is a custom filter defined with type `stemmer` and language `english`. It can be replaced with an appropriate built-in token filter, but the name and configuration must match the running Elasticsearch version.

Synonym graphs are commonly used at search time to handle synonymous phrases. Changing the synonym list at search time can adjust search behavior without reindexing all documents, provided the index configuration and analyzer update mechanism allow it.

## 8. Consequences when index analyzer and search analyzer are incompatible

Suppose the index analyzer converts:

`running` → `run`

But the search analyzer keeps it unchanged:

`running` → `running`

When a user searches for `running`, the query produces the term `running`, while the inverted index only contains the term `run`. The two terms do not match, so the document may not appear.

The opposite situation can also occur. If the search analyzer stems to `run`, while the index analyzer stores `running`, the query may fail to find the document.

Some points to keep in mind:

- The two analyzers do not have to be identical.
- They must produce tokens capable of matching according to the search intent.
- Filters such as lowercase, stemming, stop words, and synonyms can alter the token set.
- Before changing an analyzer, inspect the actual tokens with the Analyze API.

## 9. Which query types analyze their input?

Not all queries analyze input text.

| Query | Analyzes input? | Purpose |
|---|---|---|
| `match` | Yes | Full-text search |
| `match_phrase` | Yes | Phrase search by order/position |
| `multi_match` | Yes | Full-text search across multiple fields |
| `query_string` | Yes, according to analyzer and query syntax | Text query with query syntax |
| `term` | Not like a full-text query | Matches an indexed term |
| `terms` | Not like a full-text query | Matches one of multiple terms |
| `prefix` | Does not run a full-text analyzer on input | Finds terms starting with a prefix |
| `wildcard` | Does not run a full-text analyzer on input | Finds terms matching a wildcard pattern |

Example `match`:

~~~json
{
  "query": {
    "match": {
      "name": "Wireless Keyboard"
    }
  }
}
~~~

The input is analyzed using the search analyzer of the `name` field.

Example `term`:

~~~json
{
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
~~~

`term` does not pass `PUBLISHED` through a full-text analyzer. It matches against indexed terms. Therefore, when using `term` on a lowercased text field, the original uppercase value may not match the lowercase token in the index.

This is why `keyword` fields are typically used for statuses, codes, data types, and exact filter conditions.

## 10. Testing analyzers with the Analyze API

You should not just read a configuration and guess the generated tokens. Elasticsearch provides the Analyze API to inspect analysis output.

Test the index analyzer:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "analyzer": "product_index",
  "text": "TVs and wireless laptops"
}
~~~

Test the search analyzer:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "analyzer": "product_search",
  "text": "TVs and wireless laptops"
}
~~~

The returned result contains the list of tokens and metadata such as position and offset. Comparing the two results helps detect:

- Does the analyzer lowercase properly?
- Are stop words removed?
- Does stemming produce the expected root forms?
- Do synonyms expand properly?
- Are token positions suitable for phrase queries?

You can test the analyzer currently applied to a field by specifying the field name:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Testing by field is useful because Elasticsearch uses the analyzer configuration bound to that field's mapping.

## 11. Declaring analyzers in Spring Data Elasticsearch

Spring Data Elasticsearch lets you declare the analyzer and search analyzer using the `@Field` annotation.

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "product_index",
        searchAnalyzer = "product_search"
    )
    private String name;

    // Constructors, getters and setters
}
~~~

In this example:

- `type = FieldType.Text` specifies that this is a full-text field.
- `analyzer = "product_index"` selects the analyzer used at index time.
- `searchAnalyzer = "product_search"` selects the analyzer used at search time.

The analyzer names in the annotation must match analyzers defined in the index settings. The annotation only describes the field mapping; it does not automatically create custom analyzer definitions if the settings have not been configured.

One way to organize this is to manage settings using a JSON/YAML file or via the index creation flow in the application. When using the `@Setting` annotation or `IndexOperations`, make sure index settings are applied before the mapping and before writing documents.

Example of creating an index with Spring Data:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Product.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

This snippet illustrates creating an index with a mapping derived from entity metadata. If a custom analyzer requires specific settings, ensure those settings are included in the index creation process before the mapping references the analyzer.

## 12. Does changing an analyzer require reindexing?

You need to distinguish between changing the index analyzer and changing the search analyzer.

### Changing the index analyzer

The index analyzer determines the tokens stored in the inverted index. When you change the analyzer, old tokens are not automatically regenerated.

For example, previously `running` was stored as `running`; later the new analyzer converts it to `run`. If you only edit the mapping, old documents still retain the old tokens.

To keep data consistent, you typically need to:

1. Create a new index with the new settings and mapping.
2. Reindex documents from the old index to the new index.
3. Verify search results and data.
4. Switch the alias or application to the new index according to the deployment plan.

### Changing the search analyzer

The search analyzer only processes query text and does not change tokens already stored in the inverted index. Therefore, changing search-time rules may not require reindexing data.

However, updating mappings or analyzer settings is still subject to Elasticsearch's limitations and the version in use. Some settings changes require closing the index before updating; referenced analyzers/filters must also exist in settings. Check the updatability of each mapping parameter before deploying.

### Changing synonyms

If synonyms are only applied in the search analyzer, updating synonyms can often be done without reindexing documents. This is an advantage of handling synonyms at search time.

If synonyms are applied at index time, changing synonym rules will not automatically fix old tokens; reindexing is required for the data to reflect the new rules.

## 13. Common mistakes

### Using a search analyzer that produces tokens absent from the index

For example, the index analyzer applies stemming while the search analyzer does not, causing `running` and `run` not to match. Check tokens on both sides using the Analyze API.

### Assuming editing a mapping will re-analyze old documents

A new mapping only affects documents indexed after the mapping takes effect or documents that are reindexed. Old documents do not automatically change their tokens.

### Using a `term` query and expecting the analyzer to run

`term` does not behave like `match`. When full-text search is needed, choose the appropriate query.

### Placing synonyms at index time when frequent changes are expected

Index-time synonyms are tied to stored tokens. If the synonym list changes frequently, consider handling them at search time.

### Forgetting to configure custom analyzers in index settings

A mapping referencing a nonexistent analyzer name will fail to create a valid configuration. Create settings before the mapping.

### Checking only query results without inspecting tokens

When search results are wrong, the root cause may lie in the tokenizer, token filters, or search analyzer. The Analyze API helps pinpoint the issue more directly.

## 14. Design and operational workflow

When configuring text analysis for a field:

1. Identify the language and data format of the content.
2. Choose the index analyzer to produce tokens suitable for stored data.
3. Choose the search analyzer so that query tokens are compatible with tokens in the index.
4. Separate the search analyzer only when there is a reason such as synonyms or query normalization rules.
5. Decide whether a `search_quote_analyzer` is needed for phrase queries.
6. Verify results with the Analyze API before indexing large datasets.
7. Use `match` or an equivalent full-text query when input analysis is needed; use `term` for exact term matching.
8. When changing the index analyzer, plan a reindex.
9. When changing the search analyzer, verify mappings/settings and test real queries.
10. Document analyzer configurations along with index versions for reproducible and consistent operations.

## Conclusion

Index-time analysis determines the tokens stored in the inverted index; search-time analysis determines the tokens generated from query text. The two analyzers can differ, but they must produce tokens compatible with the search goal. In Spring Data Elasticsearch, you can declare them with `analyzer` and `searchAnalyzer` on `@Field`. Always verify tokens with the Analyze API, use the right query type, and remember that changing an index-time analyzer usually requires reindexing existing data.
