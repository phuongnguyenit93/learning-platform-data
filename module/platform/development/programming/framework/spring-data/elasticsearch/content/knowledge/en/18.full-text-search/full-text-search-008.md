# Fuzzy Queries, Fuzziness, and Typo Tolerance

## 1. What Problem Does Fuzzy Search Solve?

When users search, they may mistype a few characters, swap two adjacent characters, or omit a character. If a query only allows exact matches, those minor errors can prevent the application from returning results even though the desired document exists.

For example, an index contains product names:

~~~text
Wireless Headphones
Bluetooth Speaker
Mechanical Keyboard
~~~

The user enters `wirless headphones`. The word `wirless` is missing one character compared to `wireless`. An exact-matching query may fail to find the first product. Fuzzy matching allows Elasticsearch to find terms close to what the user typed within a bounded difference.

In Elasticsearch, this capability is typically configured via:

- `fuzzy` query: a term-level query finding terms similar to a specified term.
- `match` query with `fuzziness`: full-text search that analyzes the query string and applies fuzzy matching to eligible terms.
- `multi_match` with `fuzziness`: extends fuzzy search across multiple text fields for supported multi-match types.

Fuzzy search makes queries more tolerant of typos. It does not auto-correct the string the user entered, nor does it guarantee that the closest semantic match always ranks first.

## 2. What Is Edit Distance?

Fuzzy matching is based on **edit distance**: the minimum number of character edits required to transform one term into another.

Basic edit operations include:

| Operation | Example | Edit count |
|---|---|---:|
| Replace one character | `cat` → `bat` | 1 |
| Delete one character | `black` → `lack` | 1 |
| Insert one character | `sic` → `sick` | 1 |
| Transpose two adjacent characters | `act` → `cat` | 1 when transpositions enabled |

Comparison examples:

- `wireless` and `wirless`: requires inserting `e`, edit distance is 1.
- `headphones` and `headphnoes`: two adjacent characters swapped, counted as one edit when transpositions are enabled.
- `keyboard` and `keyboarx`: replace one character, edit distance is 1.
- `phone` and `phones`: insert one character, edit distance is 1.

Elasticsearch supports fuzzy matching based on edit distance. With transpositions enabled by default, swapping two adjacent characters counts as a single change. If this option is disabled, transpositions are counted more strictly.

Edit distance measures only character differences. Two words with a small distance are not necessarily synonyms or business-related. Therefore, fuzzy search is suited for typo tolerance, not as a replacement for synonyms, semantic search, or business ranking logic.

## 3. The fuzziness Parameter

`fuzziness` determines the maximum number of edits allowed between the query term and an indexed term.

Common values:

- `0`: exact match, no edits allowed.
- `1`: allows at most one edit.
- `2`: allows at most two edits.
- `AUTO`: Elasticsearch selects the distance automatically based on term length.

With the default configuration equivalent to `AUTO:3,6`, the rules by term length are:

| Term length | Maximum edits |
|---|---:|
| 0 to 2 characters | 0, must match exactly |
| 3 to 5 characters | 1 |
| Over 5 characters | 2 |

Examples:

| Search term | Length | Fuzziness under AUTO |
|---|---:|---:|
| `ki` | 2 | 0 |
| `cat` | 3 | 1 |
| `phone` | 5 | 1 |
| `wireless` | 8 | 2 |
| `elasticsearch` | 13 | 2 |

`AUTO` is usually a sensible starting point because short words are protected from overly broad expansion, while longer words can tolerate more typos.

Custom thresholds can be specified in the form `AUTO:low,high`. For example, `AUTO:4,7` adjusts the length cutoffs for allowing one or two edits. When changing thresholds, test with real data and user typing patterns.

Do not set `fuzziness: 2` by default for every query. For short words, two edits can generate far too many variants and increase irrelevant results.

## 4. Fuzzy Query: A Term-Level Query

`fuzzy` is a term-level query. It finds documents containing a term in the field close to the query value within the edit distance.

REST API example:

~~~http
GET /products/_search
{
  "query": {
    "fuzzy": {
      "sku": {
        "value": "WIRLESS",
        "fuzziness": "AUTO",
        "max_expansions": 25,
        "prefix_length": 1,
        "transpositions": true
      }
    }
  }
}
~~~

Meaning:

- `sku`: the field searched.
- `value`: the term entered by the user.
- `fuzziness`: maximum edit distance or automatic mode.
- `max_expansions`: limits the number of term variants generated.
- `prefix_length`: number of leading characters that must stay unchanged.
- `transpositions`: allows swapping two adjacent characters to count as one edit.

The `fuzzy` query generates expanded terms within the fuzziness limit, then finds documents containing any of those terms. Hence term dictionary size and expansion count affect execution cost.

### Example with a keyword field

Suppose a mapping has a user code or product code field:

~~~json
{
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

A fuzzy query on `sku` fits when codes are stored as a single keyword term. For multi-word product names, `match` with fuzziness is usually better because it analyzes the search string into tokens.

Suppose the index has SKU `WIRELESS` and the user types `WIRLESS`; a fuzzy query can find that similar term. If the keyword field has a normalizer, results also depend on the configured normalization.

Fuzzy queries do not analyze the entire search phrase like match queries. If you pass a multi-word string into a `fuzzy` query, Elasticsearch treats it as a single term value for the field instead of turning each word into an independent full-text condition.

## 5. Match Query with Fuzziness: Common Choice for Full-Text Search

For `text` fields, applications usually search a sentence or multiple words. The `match` query analyzes the query string with the search analyzer and then applies fuzzy matching per eligible term.

Example:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "name": {
        "query": "wirless headphones",
        "fuzziness": "AUTO",
        "prefix_length": 1,
        "max_expansions": 25,
        "fuzzy_transpositions": true
      }
    }
  }
}
~~~

Here:

1. Elasticsearch analyzes `wirless headphones` into tokens using the analyzer.
2. For supported terms, the query generates variants within the fuzziness limit.
3. Matching documents are returned according to match query logic and relevance score.

`match` offers additional options to control how tokens combine:

~~~json
{
  "match": {
    "name": {
      "query": "wirless headphones",
      "fuzziness": "AUTO",
      "operator": "and",
      "minimum_should_match": "75%",
      "prefix_length": 1,
      "max_expansions": 25,
      "fuzzy_transpositions": true
    }
  }
}
~~~

- `operator: "or"` allows matching one or more tokens; this is the typical default.
- `operator: "and"` requires all tokens under AND logic.
- `minimum_should_match` specifies the number or percentage of clauses that must match.
- `prefix_length`, `max_expansions`, and `fuzzy_transpositions` control fuzzy expansion.

Distinguish the two transposition parameters:

- In `fuzzy` queries, the parameter name is `transpositions`.
- In `match` queries, the parameter name is `fuzzy_transpositions`.

Do not copy the wrong parameter name between the two query types.

### Per-token fuzzy matching

In the query `wirless headphones`, the typo is in token `wirless`. Token `headphones` can match exactly. The `match` query applies fuzziness to terms after analysis, so how `OR`, `AND`, or `minimum_should_match` combines them affects results.

With `operator: "or"`, a document can match if just one token is found. With `operator: "and"`, all tokens must match. This choice should reflect the interface's search requirements.

## 6. Multi-Match Query with Fuzziness

When searching across multiple text fields, `multi_match` can be used:

~~~json
{
  "multi_match": {
    "query": "wirless headphones",
    "fields": [
      "name^3",
      "description",
      "brandName^2"
    ],
    "type": "best_fields",
    "fuzziness": "AUTO",
    "prefix_length": 1,
    "max_expansions": 25
  }
}
~~~

In this example:

- `name^3` boosts the product name field.
- `description` is searched with default weight.
- `brandName^2` prioritizes brand over description.
- `best_fields` scores results based on the best-matching field.
- `fuzziness` provides typo tolerance on eligible terms.

Not all `multi_match` types support fuzziness. For example, phrase and cross-fields types have specific restrictions. Confirm which multi-match type you are using before adding fuzziness parameters.

Fuzzy matching across multiple fields can generate more expansions than a single field. Therefore, limit the field list, apply boosts deliberately, and measure performance on real datasets.

## 7. Controlling Fuzzy Expansion

Fuzzy matching can generate many term variants. Three key parameters help bound the search space: `fuzziness`, `prefix_length`, and `max_expansions`.

### prefix_length

`prefix_length` is the number of initial characters that must match exactly and cannot be modified during fuzzy expansion.

Example for query `wireless`:

- `prefix_length: 0`: no leading character match required.
- `prefix_length: 1`: character `w` must match.
- `prefix_length: 2`: first two characters `wi` must match.

Increasing prefix length reduces expansions and improves performance. The trade-off is that if the user mistypes the very start of a word, the intended document may not be found.

For example, with `wireless` and `prefix_length: 1`, the term `vireless` will not match because the initial character differs, even though the edit distance is only one.

### max_expansions

`max_expansions` limits the number of variant terms a query is allowed to generate for a search term. The default is 50.

Do not raise this value arbitrarily. When `prefix_length` is 0 and `max_expansions` is large, the number of terms considered can grow rapidly and slow down queries.

A reasonable starting configuration might be:

~~~json
{
  "fuzziness": "AUTO",
  "prefix_length": 1,
  "max_expansions": 25,
  "transpositions": true
}
~~~

This is only a starting point for experimentation, not an optimal configuration for every index. Measure query latency, hit count, and result relevance before tuning.

### transpositions

When `transpositions` is enabled, swapping two adjacent characters counts as one edit. This is a common typo, such as `teh` instead of `the`.

- `true`: allows adjacent character transpositions, default.
- `false`: does not treat transpositions as a single edit.

In `match` queries, the corresponding parameter is `fuzzy_transpositions`.

## 8. Combining Fuzzy with Bool Queries and Filters

Full-text search often combines fuzzy matching with business rules. For instance, finding product names with typos while keeping only active products in category audio:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wirless headphones",
            "fuzziness": "AUTO",
            "prefix_length": 1,
            "max_expansions": 25
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "term": {
          "active": true
        }
      }
    ]
  }
}
~~~

`must` contains the fuzzy full-text condition and can influence score. `filter` restricts category and active status without participating in relevance scoring.

This combination lets fuzzy search tolerate typos in text while keeping exact conditions enforced on categorical or status fields.

Do not apply fuzzy queries to every field merely to make search permissive. Fields such as status, identifiers, monetary amounts, or dates generally require exact queries or range queries.

## 9. Fuzziness and Analyzers

With a `match` query, Elasticsearch analyzes the search string before fuzzy matching. Thus, the analyzer directly determines which tokens are compared.

For example, an analyzer may:

- Lowercase uppercase characters.
- Tokenize sentences into tokens.
- Remove stop words.
- Normalize diacritics or characters per configuration.
- Stem words to reduce variants to root forms.

If the analyzer removes a token or transforms a token, fuzzy matching operates on the analyzed output rather than the raw original string.

Certain cases involving synonyms or multiple tokens at the same position may not apply fuzzy expansion normally. Elasticsearch creates a special synonym query for such cases, which does not support fuzzy expansion for the corresponding terms.

Therefore, if fuzzy search fails to find expected results:

1. Check the field's mapping.
2. Use the Analyze API to inspect tokens after analysis.
3. Check synonym and stemming filters.
4. Try a match query without fuzziness to separate analyzer issues from fuzzy issues.
5. Then test `fuzziness: 1` or `AUTO` on a simple term.

For Vietnamese data, pay special attention to Unicode normalization, letter casing, diacritics, and analyzers. Fuzzy matching does not automatically understand that accented and unaccented spellings are equivalent. If business logic must support both forms, design an analyzer or dedicated normalized field and test with real data.

## 10. Fuzzy Query Is Not a Spell Checker

A fuzzy query finds documents with terms close to the query string. It does not return a corrected word to display to the user.

For example, a user types `wirless` and the query returns a document named `Wireless Headphones`. That does not mean Elasticsearch rewrote `wirless` into `wireless` in the request or response.

If the UI needs to show suggestions such as "Did you mean wireless?", use an appropriate suggester feature:

- **Term suggester:** proposes alternative terms based on the field's term dictionary.
- **Phrase suggester:** generates suggestions for phrases, using n-grams or language statistics to choose sensible phrases.
- **Completion suggester:** supports autocomplete; can configure fuzziness to tolerate typos as users type prefixes.

You can combine two flows:

1. Run fuzzy search so results still appear when users make typos.
2. If needed, run a suggester to generate spelling correction proposals.
3. Show suggestions to the user and let them select the new query.

Fuzzy matching focuses on finding documents. Suggesters focus on producing alternative words or phrases.

## 11. Using Fuzzy Queries in Spring Data Elasticsearch

Query DSL can be used with `@Query` on repositories. Example:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
    {
      "match": {
        "name": {
          "query": "?0",
          "fuzziness": "AUTO",
          "prefix_length": 1,
          "max_expansions": 25,
          "fuzzy_transpositions": true
        }
      }
    }
    """)
    List<Product> searchByNameWithTypoTolerance(String keyword);
}
~~~

`?0` is the first method parameter of the repository method. The query method substitutes the placeholder at execution time. Using `match` analyzes multi-word keywords before applying fuzzy matching.

When Query DSL control via the Java API Client is needed, build a `NativeQuery`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public SearchHits<Product> searchWithFuzziness(
        ElasticsearchOperations operations,
        String keyword) {

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query(keyword)
                .fuzziness("AUTO")
                .prefixLength(1)
                .maxExpansions(25)
                .fuzzyTranspositions(true)
            )
        )
        .build();

    return operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
    );
}
~~~

In this example, Spring Data `NativeQuery` accepts a query built with Elasticsearch Java API Client types. Method names `prefixLength`, `maxExpansions`, and `fuzzyTranspositions` correspond to match query parameters.

To use a term-level fuzzy query instead of full-text match, build a `fuzzy` clause with the NativeQuery builder:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .fuzzy(f -> f
            .field("sku")
            .value(keyword)
            .fuzziness("AUTO")
            .prefixLength(1)
            .maxExpansions(25)
            .transpositions(true)
        )
    )
    .build();
~~~

Use the `fuzzy` example for a keyword field holding a single term, such as a code or username. For multi-word searches on a text field, `match` with fuzziness is usually better.

Packages and builder APIs depend on the Spring Data Elasticsearch and Elasticsearch Java API Client versions in your project. When implementing, verify against the API of your active dependencies.

## 12. Fuzzy Matching and Relevance

Fuzzy matching widens the set of matching terms, but that does not mean the document closest in edit distance always ranks first in every case.

Elasticsearch also computes relevance scores based on the query, term frequency, field length, and other factors. A document matching multiple terms or having higher relevance can outrank a document matching only a single fuzzy variant.

You can combine fuzzy with:

- `bool.must` for primary content search.
- `bool.filter` for exact filter conditions.
- `boost` to prioritize important fields.
- `multi_match` to search across multiple fields.
- Sort by business fields when ordering is not purely score-based.

Do not apply a fixed sort by name or price when the primary goal is relevance ranking, as field sorting can prevent results from being ordered by score as expected.

When evaluating fuzzy search, build a query test set including:

- Correctly spelled words.
- Missing characters.
- Extra characters.
- Single-character substitutions.
- Swapped adjacent characters.
- Typos in the first character.
- Short words.
- Long words.
- Multi-token phrases where one token has a typo.

Observe both recall (whether target documents are found) and precision (whether too many irrelevant documents are returned). Choose fuzziness and expansion settings by balancing both goals.

## 13. Performance Limits and Cluster Settings

Fuzzy queries generate term variants and can be more resource-intensive than exact queries. Elasticsearch classifies fuzzy queries as expensive queries. If the cluster sets `search.allow_expensive_queries` to `false`, fuzzy queries may fail to execute.

Control principles:

- Use `AUTO` as a starting point instead of always allowing two edits.
- Keep `max_expansions` moderate.
- Consider `prefix_length` of 1 or higher if the data permits.
- Do not run fuzzy across too many fields simultaneously.
- Do not apply fuzzy to fields that do not need typo tolerance.
- Cap page sizes.
- Monitor latency, CPU, and hit counts during testing.
- Check `search.allow_expensive_queries` if queries are rejected.

Do not raise `max_expansions` just to force more results before understanding why the current query misses documents. Check analyzers, mappings, edit distance, and prefixes first.

## 14. Common Mistakes

**Setting fuzziness too high.** For short words, many variants can match and return irrelevant results. Use `AUTO` or limit to one edit where appropriate.

**Using fuzzy query for multi-word sentences.** `fuzzy` is a term-level query; use `match` with fuzziness when multiple tokens need analysis.

**Confusing `transpositions` and `fuzzy_transpositions`.** `fuzzy` query uses `transpositions`; `match` query uses `fuzzy_transpositions`.

**Setting `max_expansions` too large.** Many expansions increase cost, especially when `prefix_length` is 0.

**Setting prefix length too long.** If the leading character is mistyped, the query may skip the desired term. Pick prefix length based on common user typo patterns.

**Using fuzzy on unsuitable fields.** Numeric, date, or business status fields usually need typed queries. Fuzzy fits text terms or string keywords.

**Ignoring the analyzer.** Analyzers can modify or drop tokens before fuzzy matching occurs. Inspect actual tokens using the Analyze API.

**Assuming fuzzy auto-corrects keywords.** The query returns matching documents; if you want corrected word suggestions, use a suggester.

**Enabling fuzzy on every search.** Not every screen needs typo tolerance. Consider enabling it only when exact search yields no results or using a controlled combined strategy.

**Not checking `search.allow_expensive_queries`.** Cluster settings may block fuzzy queries. Verify cluster policy when queries are rejected.

## 15. Typo-Tolerant Search Design Workflow

You can implement typo tolerance in these steps:

1. Identify which fields users frequently mistype, such as product names or brands.
2. Check mappings and analyzers of those fields.
3. Start with a `match` query and `fuzziness: AUTO`.
4. Set `prefix_length` and `max_expansions` to values suited to your data.
5. Combine exact filters for category, status, or access control.
6. Test common typo patterns, including first-character typos and transposed characters.
7. Evaluate precision and recall of results.
8. Use `multi_match` only if searching multiple fields is genuinely needed.
9. Use a dedicated suggester if the UI needs corrected word or phrase proposals.
10. Monitor performance and tune settings based on real queries.

## Conclusion

Fuzzy queries help Elasticsearch find terms close to what the user entered based on edit distance. `fuzziness` caps differences; `AUTO` adapts automatically to term length. `prefix_length`, `max_expansions`, and transposition options help balance typo tolerance against performance.

For a single term on a keyword field, you can use a `fuzzy` query. For multi-word full-text search, a `match` query with fuzziness is usually better because Elasticsearch analyzes the query string before expanding terms. In Spring Data Elasticsearch, you can declare Query DSL with `@Query` or build a `NativeQuery` and execute it through `ElasticsearchOperations`.

Fuzzy matching only helps retrieve documents when typos occur. If your product needs to display spelling suggestions, add a term, phrase, or completion suggester. Good design tests real input errors, controls expansions, and monitors both result quality and performance.

## References

- [Elasticsearch — Fuzzy query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-fuzzy-query)
- [Elasticsearch — Match query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-query)
- [Elasticsearch — Fuzziness and edit distance](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/common-options#fuzziness)
- [Elasticsearch — Search suggesters](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters)
- [Spring Data Elasticsearch — Repositories and Query Methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/query-methods.html)
