# Term Suggester, Phrase Suggester, and Reading Suggest Results

Elasticsearch provides the **term suggester** and **phrase suggester** to suggest alternative spellings for user-entered text. They are commonly used to support spell checking, phrase suggestions, or displaying a “Did you mean…?” prompt in a search interface.

The two suggesters serve different purposes:

- **Term suggester** processes each token individually, finding similar terms in a field's term dictionary.
- **Phrase suggester** evaluates the entire token sequence and uses information about phrases appearing in the data to pick a correction with better context.

A suggester is not an ordinary document search query. It builds a list of suggestions from indexed data. A search request can return hits, suggestions, or both. Therefore, when reading responses, separate **hits** from **suggest** and understand what each option means.

This lesson uses the **products** index with a **name** field and a subfield for phrase suggestions. It focuses on configuring term/phrase suggesters, reading results, and integrating with Spring Data Elasticsearch.

## 1. How Do Suggestions Differ from Search Results?

A regular search query returns documents matching the query conditions. Example:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireles keybord"
    }
  }
}
~~~

If the user makes a typo, the query may not find the desired products. A suggester solves a different problem: based on already-indexed terms, it proposes closer spellings or more likely phrases.

For example, the user enters:

~~~text
wireles keybord
~~~

Term suggester can propose replacements for each word individually:

- **wireles** → **wireless**
- **keybord** → **keyboard**

Phrase suggester can propose the entire phrase:

- **wireles keybord** → **wireless keyboard**

A suggester does not automatically mean Elasticsearch found matching documents. It only generates candidate proposals from the term dictionary and statistical model. If the UI needs to know whether a suggestion actually returns products, the application can run a verification query or use **collate** with phrase suggester.

Both query and suggest can be combined in a single request:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireles keybord"
    }
  },
  "suggest": {
    "name-term": {
      "text": "wireles keybord",
      "term": {
        "field": "name"
      }
    }
  }
}
~~~

The response can contain both the **hits** section and the **suggest** section. If only suggestions are needed, set **size: 0** to omit the hit list while still receiving suggest results.

## 2. Structure of suggest in a Search Request

Suggesters are declared in the **suggest** property at the top level of a search request, alongside **query**, **from**, **size**, **sort**, and **aggs**.

Example request fetching suggestions only:

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "product-name-term": {
      "text": "wireles keybord",
      "term": {
        "field": "name",
        "suggest_mode": "always",
        "size": 3
      }
    }
  }
}
~~~

General structure:

~~~text
Search request
|
+-- query             (document matching conditions, if needed)
|
+-- from / size       (hit pagination)
|
+-- suggest
|   |
|   +-- product-name-term
|   |   |
|   |   +-- text
|   |   +-- term
|   |
|   +-- product-name-phrase
|       |
|       +-- text
|       +-- phrase
|
+-- sort / aggs / highlight / ...
~~~

Each suggester has its own name, such as **product-name-term** and **product-name-phrase**. This name serves as the corresponding key in the response so the application knows which configuration produced the results.

**text** can be placed inside each suggester or specified as shared text at the suggest level depending on the Search API structure. Per-suggester text lets each suggester evaluate different strings; shared text is convenient when term and phrase suggesters process the same string.

Distinguish two similarly named properties:

- **size** at the search request level limits the number of returned hits.
- **size** inside a suggester configuration limits the number of suggested options per entry.

Setting **size: 0** at the request level does not disable suggestions. Suggesters are still evaluated and returned in the **suggest** section.

## 3. How Does Term Suggester Work?

**Term suggester** splits the input text into tokens using the specified field's analyzer. For each token, it finds similar terms in the indexed term dictionary and ranks candidates per the configuration.

Example:

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "name-correction": {
      "text": "wireles keybord",
      "term": {
        "field": "name",
        "suggest_mode": "always",
        "size": 3
      }
    }
  }
}
~~~

Suppose the index has these names:

- Wireless Mechanical Keyboard
- Wireless Mouse
- Compact Keyboard
- Mechanical Keyboard

Term suggester can generate suggestions for each misspelled token. Results are typically returned as separate entries corresponding to token positions in the input text.

Term suggester relies on the field's term dictionary. It does not understand full linguistic context like a natural language model. If a misspelled word happens to be a valid, frequent word in the index, term suggester may not treat it as an error.

### Common Term Suggester Options

| Option | Meaning |
|---|---|
| **field** | Field used to supply the term dictionary and analyzer |
| **suggest_mode** | Controls when suggestions are generated |
| **size** | Maximum number of options per entry |
| **sort** | Sorts options by score or frequency |
| **max_edits** | Maximum edit distance when comparing terms |
| **prefix_length** | Number of leading characters that must stay unchanged |
| **min_word_length** | Minimum length of tokens to process |
| **min_doc_freq** | Minimum document frequency for a candidate |
| **max_term_freq** | Frequency threshold on the input term to consider it for suggestions |
| **max_inspections** | Candidate expansion inspection factor |
| **string_distance** | Algorithm used to measure distance between terms |
| **shard_size** | Number of candidate terms considered per shard before merging |

You do not need to set every option for every case. Start with **field**, **suggest_mode**, and **size**; tune other parameters only once you have a real query set to evaluate.

## 4. suggest_mode: missing, popular, and always

**suggest_mode** determines when term suggester produces suggestions.

| Value | Behavior |
|---|---|
| **missing** | Only suggests when the input token does not exist in the term dictionary |
| **popular** | Only suggests terms with higher frequency than the input token |
| **always** | Always searches for suggestions, even when the input token already exists |

Example with **missing**:

~~~json
{
  "term": {
    "field": "name",
    "suggest_mode": "missing"
  }
}
~~~

If the user types **wireless**, and that term already exists in the index, the suggester generally does not propose alternative spellings for that token. This mode fits basic spell-checking features.

With **popular**, Elasticsearch only returns candidates more frequent than the input token. This helps prefer common words, though it can suppress valid but rare terminology.

With **always**, the suggester looks for candidates for every token. This fits when you want suggestions even if the input word exists, though it can generate unnecessary suggestions. The UI should present them carefully so users are not confused.

If unspecified, **missing** is the common default. Verify the default of your running Elasticsearch version when consistent behavior across environments is needed.

## 5. Edit Distance and Candidate Limits

Term suggester typically uses edit distance to find similar terms. An edit can be an insertion, deletion, substitution, or transposition of characters depending on the distance algorithm.

**max_edits** caps the number of edits. Elasticsearch usually supports small values such as 1 or 2 for term suggester. Larger values increase candidate counts and processing cost, while yielding less relevant suggestions.

**prefix_length** requires a number of leading characters to match. For instance, prefix_length of 1 means candidates must keep the first character of the term. This narrows the search space.

**min_word_length** avoids processing overly short tokens. With two-letter words, a single edit can match too many unhelpful candidates.

Example:

~~~json
{
  "term": {
    "field": "name",
    "suggest_mode": "missing",
    "max_edits": 2,
    "prefix_length": 1,
    "min_word_length": 3,
    "size": 3
  }
}
~~~

Do not increase max_edits just to get more results. Inspect actual suggestions and balance finding the right spelling against the false-suggestion rate.

### sort by score or frequency

Term suggester can sort options by:

- **score**: similarity according to the string distance algorithm.
- **frequency**: occurrence frequency of the term in the index.

Choosing score prioritizes candidates closer to the input string. Choosing frequency puts more common words first even if they are not always the closest in spelling.

This sort option affects suggestion order inside each entry. It is not the search request **sort** and does not sort documents in hits.

## 6. How Fields and Analyzers Affect Term Suggester

Term suggester extracts tokens from input text using the field's analyzer. Thus, the specified field must match the language and data type.

Example **name** field as text:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "standard"
    }
  }
}
~~~

The standard analyzer splits text into tokens and applies normalization. For English, words are lowercased. Term suggester processes tokens according to the analyzer's rules.

If using a keyword field, the entire product name may be treated as a single term. Term suggester would then process the whole string rather than individual words, which does not fit fixing individual words in long names.

For Vietnamese or languages needing specialized word segmentation, the default analyzer may not produce expected tokens. Choose an analyzer suited to your language and real data. Suggesters can only propose terms that were actually produced during indexing.

When changing an analyzer, existing indices generally need to be recreated and reindexed so documents are analyzed under the new configuration. Changing annotations or settings in code alone does not reanalyze existing documents.

## 7. What Problem Does Phrase Suggester Solve?

Term suggester handles each token in isolation. It can propose several similar words, without always knowing which combination forms a valid phrase.

Suppose the user enters:

~~~text
wireles keybord
~~~

Term suggester can output:

- **wireles** → **wireless**
- **keybord** → **keyboard**

Phrase suggester considers the whole sequence and term co-occurrence statistics. It can prefer **wireless keyboard** because that phrase appears plausibly in the data, rather than piecing together choices solely by character distance.

Phrase suggester uses an n-gram language model. Therefore, the field used for phrase suggester typically needs to be indexed with an analyzer producing **shingles** (adjacent token sequences), such as bigrams or trigrams.

A suggester is not a complete semantic understanding system. Suggestion quality depends on index content, phrase frequency, analyzer, smoothing model, and configuration parameters.

## 8. Preparing a Shingle Field for Phrase Suggester

For phrase suggester to work well, create a dedicated multi-field with an analyzer using a shingle filter.

Example settings:

~~~json
{
  "analysis": {
    "filter": {
      "name_shingle": {
        "type": "shingle",
        "min_shingle_size": 2,
        "max_shingle_size": 3,
        "output_unigrams": true
      }
    },
    "analyzer": {
      "name_trigram": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase",
          "name_shingle"
        ]
      }
    }
  }
}
~~~

Mapping:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "standard",
      "fields": {
        "trigram": {
          "type": "text",
          "analyzer": "name_trigram"
        }
      }
    }
  }
}
~~~

For the text **wireless mechanical keyboard**, the shingle analyzer can emit single tokens and consecutive phrases, such as:

- unigram: **wireless**, **mechanical**, **keyboard**
- bigram: **wireless mechanical**, **mechanical keyboard**
- trigram: **wireless mechanical keyboard**

These phrase tokens let phrase suggester evaluate how likely a word sequence is to occur together in the data.

**output_unigrams: true** retains single tokens alongside shingles. Exact settings must fit your goal and Elasticsearch version. Do not apply a shingle analyzer to every text field; create a dedicated multi-field so regular full-text search keeps using an appropriate analyzer.

If an index already exists without the trigram subfield, create a new index with the appropriate mapping and settings and reindex data. You cannot expect phrase suggester to have a full n-gram model if shingle terms have not been indexed.

## 9. Configuring Phrase Suggester

Example phrase suggester for **wireles keybord**:

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "name-phrase": {
      "text": "wireles keybord",
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "gram_size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "always",
            "min_word_length": 3
          }
        ],
        "highlight": {
          "pre_tag": "<em>",
          "post_tag": "</em>"
        }
      }
    }
  }
}
~~~

Main parts:

- **field**: field holding shingle terms used to build the phrase model.
- **size**: maximum number of suggested phrases.
- **gram_size**: n-gram size matching the shingle configuration.
- **direct_generator**: source generating candidate terms for each token.
- **suggest_mode**: controls when the direct generator suggests.
- **min_word_length**: skips overly short tokens.
- **highlight**: marks changed text in options.

Phrase suggester takes candidates from the direct generator and scores combinations using the phrase model. If the field or analyzer does not emit suitable shingles, suggestion quality may suffer or the query may not behave as expected.

### Common Phrase Options

| Option | Role |
|---|---|
| **field** | Field with n-grams/shingles used for the phrase model |
| **size** | Number of phrase options returned |
| **gram_size** | Size of n-grams used in the model |
| **direct_generator** | Configuration for generating candidate terms |
| **confidence** | Relative score threshold to keep candidates |
| **max_errors** | Maximum number of tokens allowed to be corrected |
| **separator** | Token separator character in the phrase model |
| **real_word_error_likelihood** | Estimate of how likely a valid word is actually a typo |
| **force_unigrams** | Controls using unigrams when evaluating phrases |
| **token_limit** | Limits the number of tokens processed |
| **highlight** | Marks proposed changes |
| **collate** | Tests candidate phrases against a sample query |

You do not need to tune every parameter up front. Start with the shingle field, direct_generator, size, and highlight; then evaluate confidence or max_errors with real query data.

## 10. direct_generator in Phrase Suggester

Phrase suggester does not generate all candidates from scratch. **direct_generator** specifies how candidate terms are generated for each token, typically using term suggester settings.

Example:

~~~json
{
  "phrase": {
    "field": "name.trigram",
    "direct_generator": [
      {
        "field": "name.trigram",
        "suggest_mode": "always",
        "max_edits": 2,
        "prefix_length": 1,
        "min_word_length": 3
      }
    ]
  }
}
~~~

Multiple direct generators can be declared to pull candidates from different fields or configurations. Phrase suggester then combines candidates and scores the entire sequence with the n-gram model.

This explains the difference between the two suggesters:

- Term suggester returns options per token.
- Phrase suggester uses token candidates yet scores the whole phrase based on context.

If the direct generator is too broad, candidate count grows and phrase scoring cost can rise. If too narrow, phrase suggester may miss the right correction. Tune based on language, query length, and data quality.

## 11. confidence and max_errors

**confidence** controls acceptance of candidate phrases relative to the input phrase's score. A candidate must pass the relative threshold to be retained. Higher confidence makes the suggester more conservative and may return fewer suggestions.

**max_errors** limits how many tokens can be corrected in a phrase. This prevents rewriting too many words in a long query. Exact interpretation of values and bounds depends on API/version; consult the Phrase Suggester reference when tuning.

Example:

~~~json
{
  "phrase": {
    "field": "name.trigram",
    "confidence": 1.0,
    "max_errors": 1.0,
    "size": 3
  }
}
~~~

Do not set confidence too low just to get more options. More suggestions are not necessarily more helpful. A good phrase suggester should prioritize a few high-probability choices.

## 12. Using collate to Check Whether Suggestions Match Documents

Phrase suggester can use **collate** to check whether a candidate phrase matches documents. Collate runs a query template where the **{{suggestion}}** variable is replaced with the proposed phrase.

Example:

~~~json
{
  "phrase": {
    "field": "name.trigram",
    "direct_generator": [
      {
        "field": "name.trigram",
        "suggest_mode": "always"
      }
    ],
    "collate": {
      "query": {
        "source": {
          "match": {
            "name": "{{suggestion}}"
          }
        }
      },
      "prune": true
    }
  }
}
~~~

Meaning:

- Phrase suggester produces candidates.
- Collate runs a match query on the name field with the candidate text.
- **prune: true** tells the response to retain match status on candidates and remove non-matching candidates per prune API behavior.
- Collate results help the application judge whether a suggestion can actually lead to documents.

Collate increases cost because each candidate must be checked with the query template. Use it when UX requires avoiding zero-result suggestions, and cap candidate counts appropriately.

If the application applies business filters like status ACTIVE or tenant, the collate query must include those conditions if you only want suggestions that have documents within that scope. Do not assume collate automatically inherits the query/filters from the main search request.

## 13. Reading Term Suggester Responses

Suggester results reside in the **suggest** property of the response, grouped by suggester name.

Abbreviated example response:

~~~json
{
  "suggest": {
    "name-correction": [
      {
        "text": "wireles",
        "offset": 0,
        "length": 7,
        "options": [
          {
            "text": "wireless",
            "score": 0.875,
            "freq": 42
          }
        ]
      },
      {
        "text": "keybord",
        "offset": 8,
        "length": 7,
        "options": [
          {
            "text": "keyboard",
            "score": 0.875,
            "freq": 31
          }
        ]
      }
    ]
  }
}
~~~

Each entry means:

- **text**: the input token or segment being processed.
- **offset**: starting position of the segment in the input string.
- **length**: length of the input segment.
- **options**: list of proposed candidates.
- **options.text**: proposed spelling.
- **options.score**: candidate score per the suggester mechanism.
- **options.freq**: document frequency of the candidate term when returned.

Term suggester usually creates a separate entry per token. Thus, a multi-word query can have multiple entries inside a single suggester.

**A suggestion's score is not a document hit _score and is not a probability.** Do not interpret a score of 0.875 as an 87.5% chance of being right. It is an internal score used to rank candidates within the suggester algorithm.

**freq** also does not mean the number of documents guaranteed to be returned by the current query. It reflects term frequency in the index as reported by the suggester, without automatically applying business filters from the search request.

## 14. Reading Phrase Suggester Responses

Phrase suggester typically returns an entry for the entire input string with options containing proposed phrases.

Abbreviated example response:

~~~json
{
  "suggest": {
    "name-phrase": [
      {
        "text": "wireles keybord",
        "offset": 0,
        "length": 15,
        "options": [
          {
            "text": "wireless keyboard",
            "highlighted": "<em>wireless</em> <em>keyboard</em>",
            "score": 0.72,
            "collate_match": true
          }
        ]
      }
    ]
  }
}
~~~

Key fields:

- **text**: input phrase.
- **offset** and **length**: position of the phrase in the text.
- **options**: list of phrase candidates.
- **options.text**: complete proposed phrase.
- **options.highlighted**: content with highlight tags added if highlight is configured.
- **options.score**: score of the phrase candidate.
- **options.collate_match**: result of the collate check if the request used collate.

A phrase option may contain additional metadata depending on suggester and version. Do not assume every option always has **freq**, **highlighted**, or **collate_match**; these fields depend on configuration and suggester type.

### Suggestion Highlighting

With configuration:

~~~json
{
  "highlight": {
    "pre_tag": "<em>",
    "post_tag": "</em>"
  }
}
~~~

Phrase suggester can return a string with changed parts marked. The UI can use this data to highlight corrected parts prominently.

If displaying HTML, do not inject unverified highlight strings into the DOM. Use a safe renderer, handle escaping properly, and allow only application-prescribed highlight tags. Suggestion content can contain special characters from user input or indexed data.

## 15. Combining Term and Phrase Suggesters in One Request

Multiple suggesters can be declared at once to compare results at each level.

~~~http
POST /products/_search
{
  "size": 0,
  "suggest": {
    "name-term": {
      "text": "wireles keybord",
      "term": {
        "field": "name",
        "suggest_mode": "always",
        "size": 3,
        "sort": "score"
      }
    },
    "name-phrase": {
      "text": "wireles keybord",
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "gram_size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "always",
            "max_edits": 2,
            "prefix_length": 1
          }
        ],
        "highlight": {
          "pre_tag": "<em>",
          "post_tag": "</em>"
        }
      }
    }
  }
}
~~~

Term suggester returns suggestions per token; phrase suggester returns suggestions for the full phrase. The application can:

- Use term suggestions to show word-by-word corrections.
- Use phrase suggestions as a “Did you mean…?” choice.
- Compare option counts and scores across suggesters.
- Run the main query with the chosen phrase after the user confirms.

Do not automatically replace every word in the user's query without a clear policy. For search UIs, it is usually better to display suggestions and let users pick.

## 16. Reading Multiple Suggesters and Handling Empty Options

A suggester may return an entry whose **options** list is empty. That is not necessarily an error.

Common causes:

- Input token already exists and suggest_mode is missing.
- No candidates fall within the max_edits limit.
- Token is shorter than min_word_length.
- Candidates were filtered out by min_doc_freq, max_term_freq, or confidence.
- Field/analyzer has no matching terms.
- Phrase model lacks enough shingle statistics to produce good suggestions.

Example handling in the UI layer:

~~~text
If options has elements:
    Display the suggestions
If options is empty:
    Do not show the suggestion box
    Keep the original query unchanged
~~~

Do not treat empty options as an HTTP error or automatically return 404. It is a valid result of the suggestion feature.

If a request includes both query and suggest, the response can have empty hits yet still have suggestion options, or have hits with no options. The two result sections are independent in purpose and must be handled separately.

## 17. Do Term/Phrase Suggesters Inherit Query Filters Automatically?

Do not assume the suggest section automatically inherits main query conditions.

Example request whose query only searches ACTIVE products:

~~~json
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "suggest": {
    "name-phrase": {
      "text": "wireles keybord",
      "phrase": {
        "field": "name.trigram"
      }
    }
  }
}
~~~

The main query filters hits by status. The suggester, however, uses the field's term dictionary and statistical model to generate suggestions. A candidate may exist in the index while having no matching ACTIVE products.

If you only want suggestions that yield results within business scope, use collate with matching conditions or run a verification query after receiving candidates.

Example query verifying an ACTIVE candidate:

~~~json
{
  "collate": {
    "query": {
      "source": {
        "bool": {
          "must": [
            {
              "match": {
                "name": "{{suggestion}}"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "ACTIVE"
              }
            }
          ]
        }
      }
    },
    "prune": true
  }
}
~~~

Weigh the cost of checking each candidate. With only a few options, the cost can be acceptable; if candidate counts are large, cap size and evaluate load.

## 18. Using the Java API Client to Build Suggest Requests

In Spring Boot applications using Spring Data Elasticsearch 5.x, you can inject a compatible **ElasticsearchClient** to construct a SearchRequest with suggesters. This is useful when you need direct control over suggest structure and to read responses produced by the Java API Client.

Term suggester example:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.SearchRequest;
import co.elastic.clients.elasticsearch.core.SearchResponse;

SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .size(0)
        .suggest(suggest -> suggest
                .suggesters("name-term", item -> item
                        .text("wireles keybord")
                        .term(term -> term
                                .field("name")
                                .size(3)
                        )
                )
        )
);

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);
~~~

This example illustrates a suggestion-only request. **size(0)** at the SearchRequest level disables returning hits; **size(3)** inside the term suggester caps options per entry.

Phrase suggester can be declared similarly:

~~~java
SearchRequest request = SearchRequest.of(s -> s
        .index("products")
        .size(0)
        .suggest(suggest -> suggest
                .suggesters("name-phrase", item -> item
                        .text("wireles keybord")
                        .phrase(phrase -> phrase
                                .field("name.trigram")
                                .size(3)
                                .gramSize(3)
                                .directGenerator(generator -> generator
                                        .field("name.trigram")
                                )
                                .highlight(highlight -> highlight
                                        .preTag("<em>")
                                        .postTag("</em>")
                                )
                        )
                )
        )
);
~~~

Builder names, enums, and overloads may vary across Elasticsearch Java API Client versions. Use the dependency managed by Spring Boot and check the API for your project's exact version. Do not mix legacy RestHighLevelClient examples with the new Java API Client.

## 19. Reading Suggest Results from the Java API Client

The Java API Client response contains a **suggest** map, where keys are suggester names and values are lists of suggestion entries. Each entry is a union type: term, phrase, or completion depending on the suggester type.

Example iterating over term suggestions:

~~~java
import co.elastic.clients.elasticsearch.core.SearchResponse;

SearchResponse<Product> response =
        elasticsearchClient.search(request, Product.class);

var entries = response.suggest().get("name-term");

if (entries != null) {
    for (var suggestion : entries) {
        if (suggestion.isTerm()) {
            for (var entry : suggestion.term()) {
                System.out.println("Input: " + entry.text());

                for (var option : entry.options()) {
                    System.out.println(
                            option.text() + " score=" + option.score()
                    );
                }
            }
        }
    }
}
~~~

Iterating over phrase suggestions:

~~~java
var entries = response.suggest().get("name-phrase");

if (entries != null) {
    for (var suggestion : entries) {
        if (suggestion.isPhrase()) {
            for (var entry : suggestion.phrase()) {
                System.out.println("Input: " + entry.text());

                for (var option : entry.options()) {
                    System.out.println(
                            option.text() + " score=" + option.score()
                    );
                }
            }
        }
    }
}
~~~

Entry and option types are generated from the Elasticsearch Java API Client schema. Some getters may be nullable or use Optional depending on the generated client version. Verify compilation and the API reference of your actual dependency when accessing extra fields such as highlighted, freq, or collateMatch.

If the response contains multiple suggesters, look them up by the exact key set in the request. Do not rely on map iteration order or assume the first entry always belongs to a particular suggestion type.

## 20. Integrating with Spring Data Elasticsearch

Spring Data Elasticsearch provides abstractions such as **ElasticsearchOperations**, **Query**, **NativeQuery**, **SearchHits**, and converters to integrate search with Java entities. Direct suggest representation and suggest result conversion capabilities can differ across versions.

For regular search queries, Operations can be used:

~~~java
SearchHits<Product> hits =
        operations.search(query, Product.class, IndexCoordinates.of("products"));
~~~

When term/phrase suggesters are needed, check your Spring Data Elasticsearch version's API to see whether NativeQuery and SearchHits support configuring and converting suggest results. If the abstraction cannot express a needed option, use the Spring-configured **ElasticsearchClient** to send SearchRequest directly, as shown above.

A service can inject the client:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import org.springframework.stereotype.Service;

@Service
public class ProductSuggestionService {

    private final ElasticsearchClient elasticsearchClient;

    public ProductSuggestionService(
            ElasticsearchClient elasticsearchClient) {
        this.elasticsearchClient = elasticsearchClient;
    }

    // Build SearchRequest and process responses in business methods.
}
~~~

Do not create a new ElasticsearchClient per request. Use the shared configured bean to reuse connection pools, TLS, credentials, and timeouts.

If the application needs to return suggestions as DTOs to a controller, convert the response into simple application-owned types, for example:

~~~java
public record SuggestionOption(
        String text,
        Double score,
        Long frequency
) {
}
~~~

DTOs keep the controller decoupled from generated Elasticsearch Java API Client types. Depending on the suggester type, frequency or highlight may be absent; corresponding properties should be nullable or represented with appropriate types.

## 21. Designing a Suggestion Endpoint for Search UIs

A suggestion endpoint typically receives the string the user is typing and returns a short list of choices.

Example API response designed by the application:

~~~json
{
  "input": "wireles keybord",
  "suggestions": [
    {
      "text": "wireless keyboard",
      "type": "phrase",
      "score": 0.72
    }
  ]
}
~~~

This is an application response DTO, not the raw Elasticsearch response. Separating the DTO shields the UI from understanding the complex structure of the Suggest API.

A typical flow:

1. User types a string.
2. Frontend calls the suggestion endpoint after a short debounce interval.
3. Backend validates input length and limits.
4. Backend runs term or phrase suggester.
5. Backend converts options into DTOs.
6. Frontend displays a few suggestions.
7. When the user selects one, frontend submits the main search query with the chosen string.

Do not send a request to Elasticsearch on every keystroke without debouncing or rate limiting. That can generate heavy request volume, especially when suggesters must evaluate many candidates.

### When to Show Term vs. Phrase Suggestions?

- Term suggestions fit explaining per-token corrections.
- Phrase suggestions fit offering a complete, context-aware phrase.
- If phrase suggestions include collate_match, the UI can prioritize suggestions confirmed to have documents.
- If there are no options, keep the original input query and proceed with searching per application policy.

Do not auto-correct every query without informing the user. In some domains, proper names, SKUs, or internal terms might look like typos even though they are valid values.

## 22. Factors Affecting Suggestion Quality

Suggestion quality depends on multiple factors:

**Data richness.** If the index has few documents, the term dictionary and shingle statistics are not representative enough of user language.

**Analyzer.** Tokenization, lowercasing, stemming, and filters directly affect which terms the suggester sees. An unsuitable analyzer can split tokens poorly or lose information.

**Term frequency.** Common terms can be favored by frequency or sway the phrase model. Rare but valid words may get replaced by more common ones.

**Phrase context.** Phrase suggester leverages shingle statistics, yet does not understand semantic meaning like modern language models.

**Candidate parameters.** max_edits, prefix_length, min_word_length, confidence, max_errors, and size determine the candidate space and acceptance bar.

**Business filtering.** A suggestion may exist in the dictionary yet have no documents satisfying current filters. Collate or verification queries can help handle this.

If quality is poor, check the analyzer and data before widening candidate limits. Increasing max_edits or lowering confidence can increase suggestion counts while also increasing bad suggestions.

## 23. Operational Cost and Limits

Term and phrase suggesters add work to search requests. Cost depends on input text length, token count, candidate count, shard count, analyzer, and settings.

A few guidelines:

- Limit input text length.
- Cap option count with size.
- Set a suitable min_word_length to skip overly short tokens.
- Bound max_edits and max_errors.
- Avoid creating too many direct_generators.
- Only enable collate when confirming candidates have documents is necessary.
- Apply debouncing and rate limiting on the endpoint.
- Track latency separately for suggestion requests.
- Do not run suggesters on every query if unnecessary.
- Evaluate index size when adding shingle fields because indexed term counts increase.

Phrase suggester can be more resource-intensive than term suggester because it scores candidate sequences against an n-gram model. Use term suggester when only individual word correction is needed; use phrase suggester only when full-phrase context genuinely adds value.

## 24. Common Pitfalls When Using Suggesters

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Term suggester does not suggest misspelled word | Token may exist in dictionary or suggest_mode is missing | Try always/popular and inspect term dictionary |
| No suggestion options | No candidates within distance limits or token too short | Check max_edits, prefix_length, min_word_length, and data |
| Term suggester fixes individual words but phrase is still wrong | Term suggester does not evaluate full-sentence context | Use phrase suggester |
| Phrase suggester performs poorly | Field lacks shingles or gram_size mismatches | Check analyzer and subfield mapping |
| Phrase suggestions contain many poor choices | Candidate generation too broad or confidence too low | Restrict direct_generator and tune confidence |
| Suggestion has no matching documents | Suggester does not automatically apply business filters | Use collate or run a candidate check query |
| Response has hits but no suggest | Wrong suggester name, request structure, or field | Check request and suggest key in response |
| Response has only suggest, no hits | Search request set size 0 | Expected behavior when only suggestions are wanted |
| Java fails to read suggestions | Reading wrong union type or suggester key | Check isTerm(), isPhrase(), and key name |
| Highlight not shown | Highlight not configured or reading wrong option | Check highlight in phrase request and response |
| Suggestions have wrong casing | Inconsistent analyzer/normalizer | Normalize data and queries with consistent rules |
| Suggestions increase latency | Too many candidates, long tokens, or expensive collate | Limit input, size, and measure latency separately |

## 25. Workflow for Implementing Term and Phrase Suggesters

When adding suggestion capabilities to a search field, follow this sequence:

1. **Identify the need.** Fix individual words or suggest whole phrases?
2. **Choose the field.** Select an appropriate text field and analyzer.
3. **Prepare mapping.** For phrase suggester, create a shingle subfield and reindex data if needed.
4. **Build test requests.** Start with term suggester and a few basic parameters.
5. **Add phrase suggester.** Only when evaluating phrase context is needed.
6. **Read the response.** Distinguish entry, option, score, freq, highlight, and collate_match.
7. **Test with real data.** Use queries with common typos and domain proper nouns.
8. **Bound cost.** Set size, max_edits, min_word_length, and input length limits.
9. **Integrate in application.** Map suggestions to DTOs and display per UX policy.
10. **Monitor quality.** Measure suggestion selection rate, post-selection search success rate, and latency.

Term suggester fits proposing spellings per token; phrase suggester uses shingle statistics to evaluate full phrases and can produce more natural choices. In the response, **suggest** is grouped by suggester name, with each entry holding the input text and proposed options. Correctly reading **text**, **offset**, **length**, **score**, **freq**, **highlighted**, and **collate_match** lets the application present results accurately. When integrating with Spring Data Elasticsearch, use built-in abstractions if supported by your version; if direct suggest request control is needed, use the Spring-configured Elasticsearch Java API Client.
