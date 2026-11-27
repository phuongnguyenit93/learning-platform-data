# Inverted index and text search mechanics

Elasticsearch is designed to search across large volumes of text data. When an application sends a query such as `"spring data"`, Elasticsearch does not need to open each document one by one and compare the entire content. Instead, it looks up a data structure prepared during indexing: the **inverted index**.

An inverted index maps a term to the documents that contain that term. This structure allows Elasticsearch to quickly identify candidate documents, combine results from multiple terms, and rank them by relevance. To understand text search in Spring Data Elasticsearch, you need to grasp how text is analyzed when writing data, how the inverted index stores information, how queries are analyzed, and how mappings determine search behavior.

## 1. Why do we need an inverted index?

Suppose the system has three documents:

| ID | Content |
|---|---|
| D1 | Spring Data Elasticsearch |
| D2 | Elasticsearch full text search |
| D3 | Spring repository |

If documents are stored in a conventional format, a naive search approach reads each document and checks whether its content contains the search word. This approach may have to scan a huge amount of content for every query. As the number of documents and text length grow, the cost of reading and comparing increases.

An inverted index reverses how information is organized. Instead of only knowing which words each document contains, the index lets you look up a keyword to find the relevant documents:

| Term | List of documents containing the term |
|---|---|
| `data` | D1 |
| `elasticsearch` | D1, D2 |
| `full` | D2 |
| `repository` | D3 |
| `spring` | D1, D3 |
| `text` | D2 |
| `search` | D2 |

For example, when searching for `elasticsearch`, the system can look up the `elasticsearch` entry and obtain D1 and D2. When searching for both `spring` and `elasticsearch`, the system combines the corresponding document lists to determine which documents satisfy the condition.

This is a simplified example. In actual Elasticsearch, text analysis can transform content into multiple tokens, and postings lists store additional information such as term frequency and token positions.

## 2. From text to inverted index

The process of turning text into searchable data is called **analysis**. An analyzer takes input text and produces a stream of tokens. Those tokens are then used to build the inverted index for the corresponding field.

An analyzer typically consists of three components, in order:

1. **Character filters**: transform text before tokenization, such as stripping HTML tags or replacing a character pattern.
2. **Tokenizer**: splits text into tokens according to specific rules, such as splitting on word boundaries.
3. **Token filters**: modify, remove, or add tokens, such as lowercasing, removing stop words, stemming, or applying synonyms.

General diagram:

```text
Original text
    |
    v
Character filters
    |
    v
Tokenizer
    |
    v
Token filters
    |
    v
Token stream
    |
    v
Inverted index
```

### 2.1. Character filters

A character filter processes the character string before the tokenizer splits the text. Common use cases include:

- Stripping or handling HTML markup so content like `<p>Spring</p>` is not treated as searchable text.
- Normalizing specific characters or replacing character patterns according to rules.
- Converting special representations into text that the tokenizer can process consistently.

A character filter does not directly produce a word list. It prepares the input string for the tokenizer.

### 2.2. Tokenizer

A tokenizer determines token boundaries. For example, a tokenizer might split the sentence `Spring Data Elasticsearch` into three tokens:

```text
Spring | Data | Elasticsearch
```

Tokenization depends on the configured tokenizer. A word-boundary-based tokenizer handles punctuation and whitespace according to its rules; specialized tokenizers can handle different text structures.

For Vietnamese, note that spaces typically separate syllables, whereas a meaningful word can consist of multiple syllables. The standard analyzer might split `cơ chế tìm kiếm` into tokens close to `cơ`, `chế`, `tìm`, `kiếm`; it does not perform dictionary-based Vietnamese word segmentation by default or treat every multi-syllable phrase as a single lexical unit. If an application requires high Vietnamese search quality, you should evaluate suitable analyzers, plugins, or dedicated language-processing pipelines based on real data.

### 2.3. Token filters

A token filter receives the tokens produced by the tokenizer and transforms them. Common filters include:

| Filter | Effect | Illustrative example |
|---|---|---|
| `lowercase` | Converts tokens to lowercase | `Spring` → `spring` |
| `stop` | Removes stop words based on a configured list | Certain common words may be omitted |
| `asciifolding` | Converts accented characters to their ASCII equivalents | `café` → `cafe` |
| `stemmer` | Reduces words to an approximate root form using a stemming algorithm | `running` → `run` in a suitable configuration |
| `synonym` | Expands or replaces tokens using a synonym dictionary | `car` can be associated with `automobile` |

The examples above only describe each filter's purpose; actual results depend on language, configuration, and filter order. Do not enable stemming, stop words, or synonyms by default for every field. These transformations can alter meaning, precision, or phrase-matching behavior in queries.

### 2.4. Index-time and search-time analyzers

Elasticsearch can apply analyzers at two points in time:

- **Index-time analyzer** analyzes field values when a document is indexed and produces tokens stored in the inverted index.
- **Search-time analyzer** analyzes the query string before looking up the inverted index.

Normally, both analyzers should be compatible so that query tokens can match indexed tokens. Mappings allow declaring `analyzer` and, when needed, a separate `search_analyzer`. For example, a system might normalize text more aggressively at index time while using lighter rules at search time. Using different configurations must be intentional; if the output tokens are incompatible, queries may miss results.

## 3. Structure of an inverted index

An inverted index is commonly described via two main components:

- **Term dictionary**: the dictionary of indexed terms in a field.
- **Postings list**: the list of documents containing a term, along with metadata supporting queries.

For instance, after using an analyzer that lowercases and splits words, document D1 might produce the tokens `spring`, `data`, `elasticsearch`. The term dictionary has an entry `spring`; that entry's postings list indicates that D1 contains this token. Similarly, `elasticsearch` has a postings list containing D1 and D2.

An actual postings list can store more information than just document IDs:

- **Internal Document ID**: identifies a document within a Lucene segment. This ID is not the `_id` value assigned by the application to the entity.
- **Term frequency**: how many times a term appears in a document. This information supports relevance scoring.
- **Positions**: the token's position in the field. This is required for phrase queries and certain proximity queries.
- **Offsets**: the start and end character offsets of a token in the original analyzed string. This can support highlighting.

Not every field needs to store all types of metadata. A field's `index_options` setting affects how much information is stored in the index. `text` fields typically store positions to support phrase searches; other field types may use simpler levels of information.

### 3.1. Example of token positions

Suppose an analyzer produces the following tokens:

```text
D1: spring(0) data(1) elasticsearch(2)
D2: elasticsearch(0) full(1) text(2) search(3)
D3: spring(0) repository(1)
```

An illustrative postings list for `spring` can be represented as:

```text
spring ->
  D1: frequency = 1, positions = [0]
  D3: frequency = 1, positions = [0]
```

For `elasticsearch`:

```text
elasticsearch ->
  D1: frequency = 1, positions = [2]
  D2: frequency = 1, positions = [0]
```

Positions distinguish between two tokens merely co-occurring in the same document versus appearing adjacent to each other in the right order. For example, a phrase query `spring data` must check the positions of `spring` and `data`, rather than just checking whether both tokens exist in the same document.

### 3.2. Where does the inverted index live in Elasticsearch?

Elasticsearch uses Apache Lucene as the indexing and search engine in each shard. Lucene organizes indexed data into **segments**. A segment is an immutable index unit once written; subsequent writes create new data, and a merge process can combine smaller segments into larger ones.

Conceptually, each segment has its own term dictionary and postings lists. During a search, Lucene queries the relevant segments and combines the results. The segment and merge mechanism helps Lucene manage new writes, concurrent reads, and index size optimization.

Several other structures have distinct roles and should not be confused with the inverted index:

| Structure | Main purpose |
|---|---|
| `_source` | Stores the original JSON content to return documents or support other operations |
| Inverted index | Finds documents by tokens within a field |
| `doc_values` | Stores data column-wise, commonly used for sorting, aggregations, and certain queries/scripts |
| Stored fields | Stores fields explicitly configured to be stored separately for retrieval |

For example, a `text` field can be searched using the inverted index. If sorting or aggregation by the original value is needed, applications usually create an additional `keyword` field or configure an appropriate structure. `doc_values` does not replace the inverted index for full-text search.

## 4. How a text query executes

Upon receiving a query, Elasticsearch performs the following high-level steps:

1. Identify the field and query type according to Query DSL.
2. Analyze the query string using the field's search analyzer (if the query supports text analysis).
3. Look up the term dictionary to find matching terms.
4. Read postings lists to retrieve documents containing matching tokens.
5. Combine document sets according to query conditions, such as AND, OR, or phrases.
6. Calculate relevance scores if the query is scored, then select the best-matching results.
7. For distributed indices, shards process their own portions of the data; Elasticsearch aggregates the results to return to the client.

Simplified diagram:

```text
Query string
      |
      v
Search analyzer
      |
      v
Query tokens
      |
      v
Term dictionary
      |
      v
Postings lists
      |
      v
Combine matching documents
      |
      v
Score and rank
      |
      v
Search results
```

### 4.1. Match query

`match` is the query commonly used for full-text search. It analyzes the query string using the field's analyzer and searches for the corresponding tokens.

Example finding articles related to `spring data`:

```http
GET articles/_search
{
  "query": {
    "match": {
      "title": "spring data"
    }
  }
}
```

By default, `match` combines tokens using the OR operator. Therefore, a document matching one of the tokens can still be returned. You can require all tokens to match using `operator: "and"`:

```http
GET articles/_search
{
  "query": {
    "match": {
      "title": {
        "query": "spring data",
        "operator": "and"
      }
    }
  }
}
```

When more flexible rules are needed, `minimum_should_match` lets you specify the minimum number or percentage of tokens that must match.

### 4.2. Term query

`term` searches for an exact term value in the inverted index and does not automatically analyze the input string like `match`. Because of this, it is typically suited for `keyword` fields, identifiers, statuses, or pre-normalized values.

```http
GET articles/_search
{
  "query": {
    "term": {
      "category.keyword": "tutorial"
    }
  }
}
```

If the `category` field is `text`, the indexed value may have been split into multiple tokens and lowercased. Sending `term` with a raw string like `Spring Data` might not match any token. This is why you must choose the right query based on the field type and analyzer.

### 4.3. Match phrase query

`match_phrase` searches for tokens in the order and positional relationship matching the analyzed phrase. This query uses the positions information stored in the inverted index.

```http
GET articles/_search
{
  "query": {
    "match_phrase": {
      "title": "spring data"
    }
  }
}
```

If a document contains both `spring` and `data`, but the two tokens are far apart or appear in the wrong order, the document might not match the phrase. `slop` can relax the distance in some cases, though it should be used carefully to avoid returning results that stray too far from what the user entered.

### 4.4. Combining multiple conditions

A `bool` query lets you combine sub-queries:

- `must`: condition must match and can contribute to the relevance score.
- `should`: condition should match; whether it is optional or required depends on other clauses and `minimum_should_match`.
- `filter`: condition must be satisfied without calculating a relevance score; suited for filters such as status, tenant, or date.
- `must_not`: excludes documents matching the condition.

Example finding articles with the phrase `spring data` in the title and taking only published articles:

```http
GET articles/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match_phrase": {
            "title": "spring data"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "PUBLISHED"
          }
        }
      ]
    }
  }
}
```

## 5. How does Elasticsearch rank results?

Finding documents containing tokens is only part of searching. For scored queries, Elasticsearch also needs to estimate which documents are more relevant to order the results. By default, Lucene uses **BM25** as the standard similarity algorithm for text fields.

BM25 considers three main factors:

- **Term frequency (TF)**: a term appearing multiple times in a document can make that document more relevant, though the marginal benefit diminishes.
- **Inverse document frequency (IDF)**: a term that is rare across the entire document set generally has higher discriminating value than a term appearing in almost every document.
- **Field length normalization**: field length affects the score; a word appearing in a short field may be scored differently from the same frequency in a very long field.

For example, with the query `elasticsearch`, a document containing this term multiple times may receive a higher score. However, if the term appears in nearly every document, its discriminating power is low. A short document can be scored differently from a long document with the same number of occurrences.

A BM25 score is a statistical relevance score based on analyzed content, not human-like semantic understanding. Two sentences with similar meaning but no compatible tokens might not be found by a standard full-text query. When semantic search is required, you may need to combine synonyms, query expansion, or vector search depending on product requirements.

## 6. Mapping determines how a field is searched

A mapping describes the data type and how Elasticsearch indexes a field. For text search, the two most important types are `text` and `keyword`.

| Field type | How it is indexed | Use cases |
|---|---|---|
| `text` | Analyzes strings into tokens using an analyzer | Titles, descriptions, article bodies needing full-text search |
| `keyword` | Treats the entire value as a single term; can apply a normalizer | Statuses, codes, group names, categories needing exact match or aggregation |

Mapping example:

```http
PUT articles
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "status": {
        "type": "keyword"
      },
      "publishedAt": {
        "type": "date"
      }
    }
  }
}
```

In this example, `title` can be full-text searched via the analyzer. The sub-field `title.keyword` additionally stores the value as a keyword for operations needing the raw value, such as sorting or aggregations. This is **multi-fields**: a single value in `_source` is indexed in multiple ways across different fields.

You should not default every string to `text`. For example, `status = PUBLISHED` usually needs exact matching, so `keyword` is more appropriate. Conversely, long descriptions typically require `text`.

### 6.1. Distinguishing analyzer and normalizer

An analyzer processes text into one or more tokens and is typically used for `text` fields. A normalizer is for `keyword` fields; it normalizes the entire value into a single token. For example, a normalizer with a `lowercase` filter allows keyword values to be matched case-insensitively while preserving single-value semantics.

### 6.2. Changing analyzers and reindexing

The analyzer used during indexing determines the tokens stored in the inverted index. If you want to change how words are split or tokens are normalized, simply modifying application configuration is not enough to alter previously generated tokens. Typically, you must create a new index with the desired mapping/settings, run `_reindex` from the old index to the new index, and then switch aliases or update the application following an appropriate deployment process.

You cannot arbitrarily change the field type or index-time analyzer of a field that has already been created and indexed in an existing index. Therefore, mappings and analyzers should be decided before putting data into a production environment.

## 7. Declaring mappings with Spring Data Elasticsearch

Spring Data Elasticsearch provides annotations to describe indices and fields directly on entities. For example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "articles")
public class Article {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String title;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
```

The annotations express the mapping intent:

- `@Document` declares the index bound to the entity.
- `@Id` marks the entity's identifier field.
- `@Field(type = FieldType.Text)` declares a field requiring text analysis.
- `analyzer` specifies the analyzer used at index time.
- `@MultiField` declares multiple indexing strategies for the same property.
- `@InnerField` declares a sub-field, in this example `category.keyword` of type `keyword`.

The analyzer name declared in the annotation must exist in the index settings. If using a custom analyzer, it must be configured in the index settings before data is indexed. Settings can be managed via an index configuration file or via the application's own index creation process; exact API and annotation details may vary by the version of Spring Data Elasticsearch in use.

## 8. Executing searches from a repository

Once the mapping is in place, a repository can declare queries based on Elasticsearch Query DSL using the `@Query` annotation:

```java
import java.util.List;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.annotations.Query;

public interface ArticleRepository
        extends ElasticsearchRepository<Article, String> {

    @Query("{\"match\": {\"title\": {\"query\": \"?0\"}}}")
    List<Article> searchTitle(String text);

    @Query("{\"match_phrase\": {\"title\": \"?0\"}}")
    List<Article> searchTitlePhrase(String phrase);
}
```

`searchTitle` uses `match`, so the passed string is analyzed using the analyzer associated with the `title` field. `searchTitlePhrase` uses `match_phrase` to search for the phrase according to token order and positions.

A repository method derived from its method name can be convenient for simple conditions, but you should not assume every `findBy...` method generates the exact same kind of full-text query. When you need explicit control over the semantics of `match`, `term`, `match_phrase`, `bool` queries, or filters, declare an explicit query or use the query APIs of `ElasticsearchOperations`/`NativeQuery` appropriate for your library version.

## 9. Testing analyzers and queries

When search results do not match expectations, inspect the actual tokens before changing the query. Elasticsearch provides the Analyze API:

```http
POST articles/_analyze
{
  "field": "title",
  "text": "Spring Data Elasticsearch"
}
```

This API shows which tokens the field's analyzer produces. You can use it to verify lowercasing, tokenization, stop words, or synonyms.

Next, inspect the mapping:

```http
GET articles/_mapping
```

And check the search results:

```http
GET articles/_search
{
  "query": {
    "match": {
      "title": "Spring Data"
    }
  }
}
```

When troubleshooting, clarify:

- Is the field declared as `text` or `keyword`?
- Which analyzers are used at index time and at search time?
- Does the query analyze the input or require an exact term?
- Should the query match one token, all tokens, or the entire phrase in order?
- Does the target token actually exist in the index?
- Has the new data been refreshed so it can be searched?

Elasticsearch is a near real-time search engine. After writing a document, it usually appears in search results only after the next refresh. Therefore, saving an entity and immediately searching without seeing it is not necessarily a mapping or inverted index error. Appropriate refresh strategies can be used in tests; in production, weigh the cost of requesting refreshes too frequently.

## 10. Common design mistakes

### Using `term` for a `text` field

`term` does not analyze the query string like `match`. If the field has been lowercased or split into multiple tokens, the raw term may not exist in the index. Use `match` for full-text search and `term` for exact values indexed accordingly.

### Using `match` on a `keyword` field expecting word-by-word search

A `keyword` field keeps the entire value as a single term. Running `match` on this field does not turn it into an analyzed full-text field like a `text` field. If you need both full-text search and exact matching, consider multi-fields.

### Not checking the analyzer

Two strings that look similar to a user can still produce different tokens due to casing, accents, punctuation, stop words, synonyms, or tokenization rules. Use the Analyze API to inspect the output tokens instead of guessing.

### Choosing an analyzer unsuitable for Vietnamese

Splitting on whitespace may not be enough for phrase queries or compound Vietnamese words. Search quality depends on the data, how users enter queries, and business requirements. Test with a representative set of queries before selecting an analyzer or plugin.

### Expecting a new analyzer to apply automatically to existing data

Already indexed tokens do not automatically change when Java code is updated. When changing index-time analysis rules, plan to create a new index and reindex the data.

### Confusing the inverted index with data used for sorting and aggregations

The inverted index serves term lookups. Sorting and aggregations on string fields typically require `keyword` along with `doc_values`. Mapping design should consider both how data is searched and how it is read and aggregated.

## 11. Choosing a query based on requirements

| Requirement | Commonly used query/field | Notes |
|---|---|---|
| Search content containing words entered by the user | `match` on `text` | Pay attention to OR/AND operator and analyzer |
| Search for an exact phrase in order | `match_phrase` on `text` | Requires appropriate positions |
| Filter by exact status or code | `term` on `keyword` | Value must match the indexed term |
| Combine text search and metadata filtering | `bool` with `must` and `filter` | Filter conditions do not contribute to relevance score |
| Search across multiple text fields | `multi_match` | Choose fields and score combination method appropriately |
| Sort or aggregate by string | `keyword` | Typically uses `doc_values` |

## 12. Summary

The inverted index is the foundation of full-text search in Elasticsearch. When writing data, an analyzer converts text into tokens; the term dictionary maps terms to postings lists; postings lists indicate matching documents and related metadata. When searching, an analyzer processes the query string, Elasticsearch looks up the terms, combines document lists, and computes scores to rank results.

In Spring Data Elasticsearch, entity mappings determine the field types and analyzers Elasticsearch uses. `text` fits full-text search, `keyword` fits values needing exact matching, and multi-fields allow a single property to support both needs. Choosing the right mapping, analyzer, and query makes search results consistent, predictable, and well-suited to real-world data.
