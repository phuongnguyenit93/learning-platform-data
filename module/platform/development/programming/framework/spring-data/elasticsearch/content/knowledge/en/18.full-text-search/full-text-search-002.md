# Match Phrase, Word Proximity, and Term Order

In full-text search, simply having words appear anywhere in the same document is sometimes not enough. Users may want to find a phrase in exact order, such as `quick brown fox`, or allow a few intervening words between the terms in the phrase. Elasticsearch provides the **`match_phrase` query** to search by token position while allowing relaxation via the **`slop`** parameter.

In Spring Data Elasticsearch, this type of query can be built with `NativeQuery` and the Elasticsearch Java API Client. Understanding analyzers, token positions, and how slop is calculated helps you choose the right degree of flexibility while keeping results meaningful.

## 1. Regular match and match_phrase

Both `match` and `match_phrase` analyze the query string using an analyzer, but they serve different purposes:

| Query | Match condition | When to use |
| --- | --- | --- |
| `match` | Analyzed tokens can match using AND/OR operators; they do not have to be adjacent or in exact order. | Keyword-based content search where exact position is not important. |
| `match_phrase` | Tokens must match according to the positional relationship and order of the phrase, within the allowed slop. | Searching phrases, proper names, titles, or terms where word order matters. |
| `match_phrase_prefix` | Similar to a phrase query, except the last token can match as a prefix. | Phrase suggestions / autocomplete on the start of the final word. |

Suppose a document has the content:

~~~text
The quick brown fox jumps over the lazy dog.
~~~

A `match` query for `quick fox` can find the document because both words appear, even with `brown` between them. A `match_phrase` query for `quick fox` with `slop: 0` does not match because the two tokens are not at adjacent positions. If you set `slop: 1`, the phrase query can match because the token `fox` is only one step away from its expected position.

`match_phrase` does not compare literal character strings. It compares tokens and positions produced by the analyzer. Therefore punctuation, letter case, Vietnamese diacritics, or stop words can affect results depending on the analyzer configuration.

## 2. Analyzers Generate Tokens and Positions

Elasticsearch does not store `text` fields as a single string for phrase queries to compare character by character. When indexing a `text` field, the analyzer converts the string into tokens and records the position of each token in the inverted index.

For example, with a simple analyzer, the text:

~~~text
quick brown fox
~~~

can produce the tokens:

| Token | Position |
| --- | ---: |
| `quick` | 0 |
| `brown` | 1 |
| `fox` | 2 |

The phrase query `quick brown fox` at slop 0 requires the tokens to appear in this exact order and relative position. If the document is `quick red brown fox`, the positions may be `quick=0`, `red=1`, `brown=2`, `fox=3`; the original phrase query needs to shift token positions to match, and slop determines how much movement is accepted.

### 2.1. Position differs from character distance

Position is the ordinal index of a token in the analyzer stream, not a byte offset, character index, or number of spaces in the string. Multiple spaces, commas, or periods may be ignored by the tokenizer without producing separate tokens.

For instance, `quick, brown   fox` still typically has tokens at positions 0, 1, 2 with the standard analyzer. A phrase query can match even when punctuation and whitespace counts differ.

### 2.2. Field analyzer and search analyzer

The analyzer used at indexing time creates tokens/positions stored in the inverted index. When running `match_phrase`, the query string is also analyzed by the field's search analyzer (or an analyzer specified in the query). Both sides must have compatible rules.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard",
        "search_analyzer": "standard"
      }
    }
  }
}
~~~

If the index analyzer and search analyzer differ, a phrase query can still work, but positions and tokens must be designed intentionally. Changing the analyzer after data is already indexed does not regenerate old tokens; when changing index-time analysis, you generally need to create a new index and reindex.

## 3. `match_phrase` Syntax and the `slop` Parameter

Basic Query DSL:

~~~json
{
  "query": {
    "match_phrase": {
      "title": "quick brown fox"
    }
  }
}
~~~

You can use the object form to control `slop`, analyzer, and boost:

~~~json
{
  "query": {
    "match_phrase": {
      "title": {
        "query": "quick brown fox",
        "slop": 1,
        "analyzer": "standard",
        "boost": 2.0
      }
    }
  }
}
~~~

Important parameters:

| Parameter | Meaning |
| --- | --- |
| `query` | The text phrase to analyze into tokens. |
| `slop` | Number of positional moves allowed for tokens to match the phrase. Default is `0`. |
| `analyzer` | Overrides the analyzer used to analyze the query text; if omitted, Elasticsearch uses the field's search analyzer per mapping rules. |
| `boost` | Adjusts the relevance weight of the query relative to other queries. |
| `zero_terms_query` | Defines behavior if the analyzer removes all tokens; common default is `none`. |

`slop: 0` requires tokens to match at exact relative positions with no extra gaps. Increasing slop allows tokens to shift positions so the phrase still matches.

## 4. How Does Slop Measure Distance?

Slop is the cost of moving token positions to transform the positions in the document into the positional relationship required by the phrase query. It can be roughly thought of as flexibility in distance and order, but **slop does not simply equal the number of words between two words**.

Example query:

~~~json
{
  "query": {
    "match_phrase": {
      "title": {
        "query": "quick fox",
        "slop": 1
      }
    }
  }
}
~~~

The document `quick brown fox` has token `quick` at position 0 and `fox` at position 2. To match the phrase `quick fox`, token `fox` must shift one position toward the desired relationship; slop 1 is enough to accept this case.

With query `quick brown fox`, document `quick brown red fox` has one extra token between `brown` and `fox`. Slop 1 can allow the phrase to match with a single position shift.

### 4.1. Slop 0

Slop 0 is the strictest option: tokens must appear in exact order and adjacent relative positions after analyzer processing.

| Document | Query `quick brown fox`, slop 0 |
| --- | --- |
| `quick brown fox` | Matches. |
| `quick brown red fox` | Does not match because an extra token sits in between. |
| `brown quick fox` | Does not match because order changed. |
| `quick, brown fox` | Usually matches because punctuation does not create separate tokens with the standard analyzer. |

### 4.2. Slop greater than 0

Slop greater than 0 allows tokens to be separated by a gap or shift relative positions. This is useful when authors may insert minor words while keeping the main phrase close together.

Example:

| Document | Query `quick brown fox` | Notes |
| --- | --- | --- |
| `quick brown fox` | slop 0 | Exact positional match. |
| `quick brown red fox` | slop 1 | Can match with one positional shift. |
| `quick very brown red fox` | small slop | Needs more shifts; increase slop according to actual positions. |
| `fox brown quick` | low slop | Does not match; reversing order requires higher cost. |

When choosing slop, test on a representative set of sentences using `_analyze` and real queries. Do not pick a large number just to increase result counts, because phrases whose key words are reversed or far apart may also begin matching.

### 4.3. Word transposition

A phrase query with slop greater than 0 can accept certain cases where tokens swap order. In Elasticsearch's slop calculation, swapping two adjacent tokens has a cost of 2.

For example, query `quick brown` and document `brown quick` do not match at slop 0. Slop 2 can accept swapping these two tokens. Therefore, if the business requirement demands exact word order, use slop 0.

A large slop does not just mean "allow N extra words". It also lets tokens shift positions and, when the cost budget is high enough, change order. Consider linguistic meaning before increasing slop.

## 5. Word Appearance Order

With slop 0, `match_phrase` preserves token order as given in the query phrase. For example, query `spring data elasticsearch` matches the phrase in that exact order after the analyzer runs.

| Document content | Query `spring data elasticsearch`, slop 0 |
| --- | --- |
| `Spring Data Elasticsearch` | Matches. |
| `Learn Spring Data Elasticsearch` | Matches because the phrase appears consecutively inside the sentence. |
| `Elasticsearch Spring Data` | Does not match because order differs. |
| `Spring Elasticsearch Data` | Does not match because relative positions differ. |
| `Spring Data for Elasticsearch` | Does not match at slop 0 because token `for` sits in between. |

With an appropriate slop, a document with a few intervening words between tokens can still match. If order reversal is allowed, slop must be large enough to pay the cost of that movement.

## 6. Using `match_phrase` in Spring Data Elasticsearch

With Spring Data Elasticsearch using the Elasticsearch Java API Client, a phrase query can be built via `NativeQuery`.

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text, analyzer = "standard",
            searchAnalyzer = "standard")
    private String title;

    @Field(type = FieldType.Text, analyzer = "standard")
    private String content;

    // Constructor, getters, and setters
}
~~~

Build a phrase query with slop 0:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.matchPhrase(mp -> mp
                .field("title")
                .query("spring data elasticsearch")
                .slop(0)))
        .build();
~~~

Execute via `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<ArticleDocument> findExactPhrase(
        ElasticsearchOperations operations) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.matchPhrase(mp -> mp
                    .field("title")
                    .query("spring data elasticsearch")
                    .slop(0)))
            .build();

    return operations.search(query, ArticleDocument.class);
}
~~~

To allow intervening tokens, you can change slop:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.matchPhrase(mp -> mp
                .field("content")
                .query("spring data elasticsearch")
                .slop(2)))
        .build();
~~~

Builder methods are generated from the Elasticsearch Java API Client. Method names and parameter types must match the client version managed by Spring Data Elasticsearch in the project.

## 7. Using Phrase Queries in Repositories/Services

For phrase queries with a fixed structure, the logic can be placed in a custom repository fragment or dedicated search service. This lets callers pass only the phrase without building Query DSL themselves.

Example service:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ArticleSearchService {

    private final ElasticsearchOperations operations;

    public ArticleSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ArticleDocument> searchTitlePhrase(String phrase) {
        NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q.matchPhrase(mp -> mp
                        .field("title")
                        .query(phrase)
                        .slop(0)))
                .build();

        return operations.search(query, ArticleDocument.class);
    }
}
~~~

You can extend the method to accept a use-case-selected slop, but the value should be bounded within a reasonable range. Do not let clients pass an arbitrarily large slop, as that can make queries broader than desired and increase search cost.

## 8. Combining Phrase Queries with Filter Conditions

A phrase query typically handles content search and can participate in the relevance score. Conditions such as tenant, status, article type, or publication date usually just constrain the result set.

They can be combined using `bool.must` and `bool.filter`:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match_phrase": {
            "title": {
              "query": "spring data elasticsearch",
              "slop": 0
            }
          }
        }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } },
        { "term": { "language": "vi" } }
      ]
    }
  }
}
~~~

In Spring Data, create a NativeQuery:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.matchPhrase(mp -> mp
                        .field("title")
                        .query("spring data elasticsearch")
                        .slop(0)))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("PUBLISHED"))))
                .filter(f -> f.term(t -> t
                        .field("language")
                        .value(FieldValue.of("vi"))))))
        .build();
~~~

The phrase query determines how well the phrase matches; filters only exclude documents with the wrong status or language. Results can be ranked by the score from the phrase query.

## 9. Impact of Analyzers on Phrase Matching

A phrase query can only work accurately when you understand how the analyzer produces tokens and positions. Several configurations deserve attention:

### 9.1. Lowercase and asciifolding

An analyzer with `lowercase` helps `Spring`, `SPRING`, and `spring` produce compatible tokens. `asciifolding` can normalize certain accented characters to their approximate ASCII forms.

For example, if both index analyzer and search analyzer convert to lowercase, a query for `Spring Data` can match a document containing `SPRING DATA`. Diacritic stripping depends on the analyzer and language; test with real Vietnamese data rather than assuming all diacritics normalize the same way.

### 9.2. Stop words and position gaps

A stop filter can remove common words such as `the`, `of`, and `and`. When removing a stop word, the analyzer can preserve the positional gap through position increments.

For instance, after removing `of` and `the`, the sentence `state of the art` may leave tokens `state` and `art`, while the position of `art` still reflects the gap from the removed words. The phrase query `state art` is therefore not necessarily equivalent to two adjacent tokens; behavior depends on the analyzer configuration and whether position increments are preserved.

You should not arbitrarily disable position increments just to make phrase queries match more easily, because doing so can make distant words appear positionally adjacent.

### 9.3. Synonyms and synonym graphs

Synonyms can expand a word into multiple alternatives or a multi-token phrase. For multi-word synonyms, the `synonym_graph` filter is designed to preserve the token graph structure needed for phrase queries.

For example, `ny` and `new york` can be declared as equivalent forms. When the analyzer applies synonym graph, phrase queries can evaluate the corresponding token paths. Verify with `_analyze` and sample queries because filter order, synonym configuration, and search analyzer directly affect results.

### 9.4. Tokenizer and language

The `standard` tokenizer works well for many kinds of natural text, but it is not a specialized word segmenter for every language. For Vietnamese, you need to test phrases with diacritics, without diacritics, compound words, proper names, and how users enter queries.

If the analyzer creates tokens different from how users perceive phrases, `match_phrase` may not yield expected results even if the strings look identical to the eye. In that case, adjust the analyzer or use an appropriate language analysis plugin.

## 10. Text Arrays and Gaps Between Values

A `text` field can hold multiple values, such as an array of titles or string tags. Elasticsearch uses `position_increment_gap` to insert a positional gap between values in the same field, preventing phrase queries from matching across the boundary between two values.

Example document:

~~~json
{
  "aliases": [
    "spring data",
    "elasticsearch guide"
  ]
}
~~~

By default, Elasticsearch typically places a large position gap between values of the same field (100 by default). Thus a phrase query `data elasticsearch` with normal slop will not match across the end of the first value and the start of the second value.

You can configure the gap on a text field:

~~~json
{
  "mappings": {
    "properties": {
      "aliases": {
        "type": "text",
        "position_increment_gap": 100
      }
    }
  }
}
~~~

This is a mechanism to control phrase positions, not a security boundary. If slop is set larger than the gap, a phrase query can cross that distance. Choose the gap and slop limit according to your data semantics.

## 11. Fields Must Store Positions

Phrase queries require token position information in the inverted index. For `text` fields, the default `index_options` usually stores positions. If a mapping lowers `index_options` to a level that does not store positions, phrase queries cannot work as intended.

Typical mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "body": {
        "type": "text",
        "index_options": "positions"
      }
    }
  }
}
~~~

Normally you do not need to declare `index_options` because the default for `text` already supports phrase queries. Change it only when you understand the impact on phrase, span, and other position-dependent queries.

## 12. Inspecting Tokens with `_analyze`

When a phrase query does not return expected results, check the analyzer first. Example:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "field": "title",
  "text": "Spring Data for Elasticsearch",
  "explain": true
}
~~~

The `_analyze` response shows tokens along with position, offset, and type information. Check:

- Which tokens were produced?
- How were letter case and diacritics normalized?
- Were stop words removed?
- Do token positions preserve gaps?
- Did synonyms create multiple token paths?

You can directly test a declared analyzer:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "standard",
  "text": "quick brown fox"
}
~~~

When `field` is specified, Elasticsearch uses the analyzer bound to that field by the mapping. When `analyzer` is specified, the request targets that specific analyzer. Compare the output between the index-time analyzer and search-time analyzer to find the cause of phrase mismatches.

## 13. Comparing `match_phrase`, `match_phrase_prefix`, and `span_near`

| Query | Capability | Use case |
| --- | --- | --- |
| `match_phrase` | Matches token sequence in order and position, with slop. | Searching complete phrases. |
| `match_phrase_prefix` | Like phrase query, except the last token is matched as a prefix. | Phrase autocomplete. |
| `span_near` | Combines span clauses with finely controlled distance and order. | Complex positional queries, multiple branches, or advanced positional logic. |

Do not use `match_phrase_prefix` as a default replacement for phrase queries. A prefix on the final token can expand the number of terms examined and make the query more expensive.

`span_near` is appropriate when exact control over distance, order, and positional clause types is required. This query is more complex and usually requires `NativeQuery` or direct Query DSL.

## 14. Impact on Relevance Score

`match_phrase` operates in query context and can contribute to `_score`. Documents matching the phrase close to the requested positions generally achieve better relevance under phrase query scoring.

You can boost a phrase query when an exact phrase should weigh more than regular keyword matches:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "match": {
            "content": {
              "query": "spring data elasticsearch"
            }
          }
        },
        {
          "match_phrase": {
            "title": {
              "query": "spring data elasticsearch",
              "slop": 0,
              "boost": 3.0
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

Here, `match` finds documents with relevant tokens in the content; `match_phrase` prioritizes documents with the exact phrase in the title. Boost values are illustrative and should be tuned based on data, relevance evaluation, and user behavior.

## 15. Common Pitfalls

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `match_phrase` does not match even though all words are in the document | Words are not adjacent, wrong order, or slop is insufficient. | Inspect positions and increase slop in a controlled way if business rules allow. |
| Phrase matches despite different punctuation | Analyzer strips punctuation or normalizes the string. | This is token-based behavior; inspect `_analyze` if punctuation must be distinguished. |
| Query is unexpectedly case-sensitive | Index/search analyzers do not use compatible lowercasing. | Check analyzers on both sides and configure lowercase if appropriate. |
| Accented and unaccented words do not match | Analyzer has not applied appropriate folding or language needs custom handling. | Test `asciifolding` with real language datasets. |
| Phrase query matches across two array values | Slop is large enough to exceed `position_increment_gap`. | Choose a gap and slop cap suited to the data structure. |
| Phrase query errors about positions | Field mapping does not store positions in index options. | Use a `text` mapping supporting positions and reindex the data. |
| Phrase query on `keyword` does not act like a phrase | Keyword analyzer treats the entire string as a single token. | Use a `text` field or an appropriate multi-field. |
| Increasing slop makes results too broad | Slop allows tokens to shift positions and potentially swap order. | Reduce slop; use slop 0 if order is mandatory. |
| Synonyms cause unexpected phrase matching | Incompatible token graph or filter order. | Inspect the analyzer with `explain` and configure `synonym_graph`. |

## 16. Phrase Search Design Process

When adding phrase search to a field, follow this sequence:

1. Determine whether users need an exact phrase or can tolerate intervening words.
2. Choose a `text` field mapping with an appropriate analyzer; ensure the inverted index stores positions.
3. Verify that the index analyzer and search analyzer produce compatible tokens.
4. Use `match_phrase` with slop 0 if exact order and adjacent positions are required.
5. Increase slop only when the business logic allows gaps or positional shifts; remember slop is token movement cost, not simply intervening word count.
6. If strict order is critical, avoid slop large enough to allow transposition.
7. For text arrays, consider `position_increment_gap` to prevent phrase queries from crossing value boundaries.
8. Inspect stop words, synonyms, and token positions using `_analyze`.
9. Use NativeQuery in Spring Data when you need explicit phrase queries or bool/filter combinations.
10. Evaluate results and relevance on a representative query set before release.

`match_phrase` searches for tokens by positional relationship and order, while `slop` lets them shift within a cost budget. Slop 0 suits consecutive, ordered phrases; higher slop tolerates gaps and can allow order swaps when cost permits. In Spring Data Elasticsearch, `NativeQuery` expresses phrase queries clearly; `_analyze` is the essential tool to inspect the tokens and positions an analyzer actually generates.
