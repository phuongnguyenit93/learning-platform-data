# Designing Autocomplete and Spell Correction Suggestions

Autocomplete helps users find the right content when they have typed only part of a query. Spell correction suggests a more likely spelling when a user makes a typo. Both features frequently appear side by side in a search box, yet they have distinct goals and mechanisms.

Elasticsearch provides several ways to build suggestions:

- **Completion suggester**: optimized for low-latency prefix suggestions, well suited for product names, brands, or navigation phrases.
- **search_as_you_type**: creates subfields for multi-word in-progress queries, supporting both prefix and infix matching.
- **Term suggester**: proposes replacement words based on edit distance.
- **Phrase suggester**: picks corrections for an entire phrase using n-gram co-occurrence models.
- **Fuzzy completion**: allows the completion suggester to tolerate minor typos in the prefix.

Spring Data Elasticsearch supports mapping completion fields, building queries with NativeQuery and the Elasticsearch Java API Client, and reading results through SearchHits. When implementing these features, choose the right suggester for the UX, cap result counts, and control language, tenant isolation, ranking, and query cost.

## 1. Distinguishing Autocomplete and Spell Correction

### 1.1. Autocomplete Predicts the Rest of the Query

The user has just typed:

~~~text
wireless key
~~~

Autocomplete might suggest:

- Wireless Keyboard
- Wireless Keyboard Compact
- Wireless Keypad
- Wireless Keyboard Bluetooth

The goal is to help the user finish typing faster. Results are usually entity names or phrases that can be selected immediately.

### 1.2. Spell Correction Fixes Typos Already in the Query

The user types:

~~~text
wirless keybord
~~~

Spell correction might suggest:

~~~text
Did you mean "wireless keyboard"?
~~~

The goal is to find a spelling close to the input that has a higher probability of being right based on the dictionary and data context.

### 1.3. The Two Features Should Have Separate Flows

| Scenario | Suitable mechanism | Example |
|---|---|---|
| User is typing a prefix | Completion suggester | "wire" → "Wireless Keyboard" |
| User types multiple words in flexible order | search_as_you_type | "wire key" → "Wireless Keyboard" |
| User mistypes a single token | Term suggester or fuzzy completion | "keybord" → "keyboard" |
| Need phrase correction using context | Phrase suggester | "wireles keybord" → "wireless keyboard" |
| Need search results even before picking a suggestion | Normal search query | Search with current input |

Do not silently rewrite the user's query every time a suggester returns a candidate. Usually you should display the suggestion for the user to choose or run correction as an observable fallback branch.

### 1.4. Suggestion UI Flow

~~~mermaid
flowchart TD
    A[User types text] --> B{Input length sufficient?}
    B -->|No| C[Wait for more characters]
    B -->|Yes| D[Autocomplete query]
    D --> E[Show top suggestions]
    E --> F{User selects suggestion?}
    F -->|Yes| G[Run search with selected value]
    F -->|No| H[User submits raw query]
    H --> I[Run normal search]
    I --> J{Few or no useful results?}
    J -->|Yes| K[Run spell correction]
    J -->|No| L[Show search results]
    K --> M[Offer corrected query]
~~~

Autocomplete typically runs with debouncing while the user types. Spell correction can run upon submit or when search yields few results, avoiding expensive correction calls on every keystroke.

## 2. Choosing an Autocomplete Mechanism in Elasticsearch

### 2.1. Completion Suggester

The completion suggester uses a **completion** field mapping and an in-memory-optimized data structure for fast prefix lookups.

Suitable when:

- Suggesting product names, brands, locations, or popular queries.
- Returning a short list while the user types.
- Ranking suggestions with weights.
- Using fuzzy options to tolerate minor typos in the prefix.

The completion suggester prioritizes speed and consumes memory because completion structures reside in memory. It is a navigation/autocomplete feature, not a replacement for general spell correction.

### 2.2. search_as_you_type

The **search_as_you_type** field type automatically creates subfields such as:

- The analyzed root field.
- A 2-gram shingle subfield.
- A 3-gram shingle subfield.
- A prefix index subfield.

The common query is **multi_match** with type **bool_prefix** across the root field and shingle subfields. This supports both prefix completion and infix completion in multi-word values.

Suitable when:

- Users type multiple words.
- Typed words may appear at different positions within the field.
- You want to use standard Query DSL instead of a separate suggester.
- You need to combine suggestions with filters, scoring, or other queries.

### 2.3. Edge N-Gram Analyzer

Edge n-grams generate prefix tokens at index time. For example, the word keyboard can produce:

~~~text
ke
key
keyb
keybo
keyboa
keyboard
~~~

At query time, a normal analyzer looks up matching tokens.

This approach is flexible, though it increases the number of indexed terms and index size. Index-time and search-time analyzers must be configured properly; applying edge n-grams on both sides can skew results.

### 2.4. Comparing the Three Options

| Criterion | Completion suggester | search_as_you_type | Edge n-gram |
|---|---|---|---|
| Mapping | completion | search_as_you_type | text + custom analyzer |
| Prefix speed | Very well suited | Suitable | Depends on index and query |
| Infix/multi-term | Limited by completion input | Supported | Can be designed |
| Fuzzy prefix | Has fuzzy options | Not a primary typo mechanism | Requires separate fuzzy query |
| Ranking weight | Dedicated weight | Uses query score | Uses query score |
| Index cost | Completion structure, memory | Multiple subfields | Many tokens |
| Use case | Navigation suggestion lists | Search-as-you-type on text | Custom prefix search |

You do not need to deploy all three for the same field. Pick according to data shape, UX, and latency requirements.

## 3. Mapping Completion Fields with Spring Data

### 3.1. Using @CompletionField

Spring Data Elasticsearch provides the **@CompletionField** annotation and **Completion** type:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions-v1")
public class ProductSuggestionDocument {

    @Id
    private String id;

    private String productName;

    @CompletionField(maxInputLength = 100)
    private Completion suggest;

    // Getters and setters.
}
~~~

The completion field indexes one or more input strings for suggestions. maxInputLength caps the input length indexed to avoid bloated completion structures from oversized data.

### 3.2. Completion with Multiple Inputs and Weight

A single document can have multiple names:

~~~java
Completion completion =
    new Completion(List.of(
        "Wireless Keyboard",
        "Wireless Keyboard Compact",
        "Bluetooth Keyboard"
    ));

completion.setWeight(100);
document.setSuggest(completion);
~~~

Weight is a positive integer used to rank suggestions. It can derive from popularity, business priority, or precomputed quality signals.

Avoid assigning excessively high weights to an item just to force it to the top if that makes suggestions less relevant. Measure suggestion click-through and conversion rates to tune ranking.

### 3.3. Indexing Aliases and Alternative Names

A product can be suggested via:

- Official name.
- Abbreviations.
- Unaccented name.
- Popular aliases.
- Model name.
- Legacy name if users still search for it.

Example:

~~~java
Completion completion =
    new Completion(List.of(
        "Ho Chi Minh City",
        "HCMC",
        "Saigon",
        "Thành phố Hồ Chí Minh"
    ));
~~~

All these inputs attach to the same document ID. When the user selects a suggestion, the application can retrieve the document ID to navigate or execute an exact search.

### 3.4. Do Not Index Arbitrary Variants

Do not generate hundreds of permutations per document. Only index aliases with genuine search value. Too many inputs inflate completion structures and return noisy suggestions.

Normalize casing, whitespace, and punctuation consistently. For Vietnamese, decide explicitly whether to index both accented and unaccented forms or use an appropriate analyzer/normalization. Never assume a lowercase filter strips Vietnamese diacritics.

### 3.5. Building Suggestion Documents from a Domain Model

Example mapper:

~~~java
public ProductSuggestionDocument toSuggestion(Product product) {
    ProductSuggestionDocument document =
        new ProductSuggestionDocument();

    document.setId(product.getId());
    document.setProductName(product.getName());

    Completion completion = new Completion(
        List.of(
            product.getName(),
            product.getSearchAlias()
        )
    );
    completion.setWeight(product.getPopularityWeight());

    document.setSuggest(completion);
    return document;
}
~~~

This is a structural example. In production, drop null/empty aliases and deduplicate inputs before indexing. Suggestion projections should be updated whenever source names or aliases change.

## 4. Querying the Completion Suggester via NativeQuery

### 4.1. Building a Suggester with the Elasticsearch Java API Client

NativeQueryBuilder provides **withSuggester**, accepting a Suggester from the Elasticsearch Java API Client.

Example completion query:

~~~java
import co.elastic.clients.elasticsearch._types.SuggestMode;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Suggester suggester = Suggester.of(s -> s
    .suggesters("product-completion", field -> field
        .prefix(prefix)
        .completion(completion -> completion
            .field("suggest")
            .size(10)
            .skipDuplicates(true)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();

SearchHits<ProductSuggestionDocument> hits =
    operations.search(query, ProductSuggestionDocument.class);
~~~

Builder method names and generated types can vary across Elasticsearch Java API Client versions. If imports or overloads do not match, inspect the Javadoc for the client managed by your Spring Data release train. Do not override the client dependency independently just to make a snippet compile.

### 4.2. Prefix and Suggestion Count

In the example:

- prefix is the text the user has typed.
- field is the completion field name in the mapping.
- size caps the number of suggestions.
- skipDuplicates filters out duplicate suggestion text in the response.

Keep size small—usually a handful to a couple dozen results. Returning too many suggestions inflates payloads and makes UI selection harder.

### 4.3. Reading Suggestions from SearchHits

Spring Data returns suggest responses via **SearchHits.getSuggest()**:

~~~java
Suggest suggest = hits.getSuggest();

if (suggest != null) {
    Suggest.Suggestion<?> suggestion =
        suggest.getSuggestion("product-completion");

    if (suggestion != null) {
        for (var entry : suggestion.getEntries()) {
            for (var option : entry.getOptions()) {
                String text = option.getText();
                Double score = option.getScore();
                // Map text and score to an API response DTO.
            }
        }
    }
}
~~~

The suggestion response is separate from the document hits list. A search can return hits, suggestions, or both depending on the request. Check for nulls and match the declared suggestion name when parsing.

### 4.4. Returning Small DTOs to the Frontend

You do not need to return full entities just to display suggestions. A DTO can include:

~~~java
public record SearchSuggestion(
    String id,
    String text,
    String type,
    double score
) {
}
~~~

You can extract the document ID from the completion option if the response attaches the search hit to the option in your version. If only text is needed, return the text and suggestion type. When the user selects one, the frontend sends the chosen ID or text to the search endpoint.

## 5. Fuzzy Completion for Typo Tolerance

### 5.1. What Is Fuzzy Completion?

The completion suggester offers a fuzzy option to tolerate minor typos in the prefix. For instance, the user types:

~~~text
wirless key
~~~

Fuzzy completion can suggest Wireless Keyboard if the prefix is long enough and fuzzy settings permit it.

### 5.2. Fuzzy Completion Example via NativeQuery

~~~java
Suggester suggester = Suggester.of(s -> s
    .suggesters("product-completion", field -> field
        .prefix(prefix)
        .completion(completion -> completion
            .field("suggest")
            .size(8)
            .skipDuplicates(true)
            .fuzzy(fuzzy -> fuzzy)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
~~~

This snippet enables default client/server fuzzy options. When tuning is needed, common settings include fuzziness, transpositions, min_length, and prefix_length. Exact enum and builder method names depend on client version.

### 5.3. Bounding Fuzzy to Prevent Noisy Suggestions

Fuzzy matching increases candidate expansion and cost. Best practices:

- Enable it only after the prefix reaches a minimum length.
- Require the leading prefix characters to match exactly.
- Cap edit distance.
- Cap the number of suggestions.
- Never apply fuzzy matching to identifiers requiring exact matches.
- Prefer exact completion results over fuzzy ones when displaying suggestions.

Do not apply fuzzy correction to short inputs like "a" or "ip" because there are too many possible interpretations.

### 5.4. Transposition

Fuzzy completion can count swapping two adjacent characters as a single edit depending on the transpositions setting.

Example:

~~~text
keybaord -> keyboard
~~~

This is helpful for common typing mistakes. However, fuzzy matching does not understand semantics; it strictly finds strings close by edit distance.

## 6. search_as_you_type for Multi-Word Queries

### 6.1. Mapping

Spring Data provides FieldType.Search_As_You_Type:

~~~java
@Document(indexName = "catalog-suggest-v1")
public class CatalogSearchDocument {

    @Id
    private String id;

    @Field(type = FieldType.Search_As_You_Type)
    private String name;

    @Field(type = FieldType.Keyword)
    private String categoryId;
}
~~~

Elasticsearch generates subfields for shingles and prefixes. Equivalent JSON mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "search_as_you_type",
        "max_shingle_size": 3
      },
      "categoryId": {
        "type": "keyword"
      }
    }
  }
}
~~~

Subfields typically take the form name._2gram, name._3gram, and name._index_prefix. You do not need to declare each subfield explicitly in the entity.

### 6.2. The bool_prefix Query

The typical query is multi_match with type bool_prefix:

~~~json
{
  "query": {
    "multi_match": {
      "query": "wireless key",
      "type": "bool_prefix",
      "fields": [
        "name",
        "name._2gram",
        "name._3gram"
      ]
    }
  }
}
~~~

Words can match in various positions; shingle subfields boost scores when words appear in sequence.

### 6.3. NativeQuery with bool_prefix

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .multiMatch(m -> m
            .query(prefix)
            .type(TextQueryType.BoolPrefix)
            .fields(
                "name",
                "name._2gram",
                "name._3gram"
            )
        )
    )
    .withPageable(PageRequest.of(0, 10))
    .build();

SearchHits<CatalogSearchDocument> hits =
    operations.search(query, CatalogSearchDocument.class);
~~~

Enum and builder types must match your Elasticsearch Java API Client version. If code fails to compile, consult the generated API docs rather than randomly altering query semantics.

### 6.4. Prefix and Infix

search_as_you_type supports both prefix completion and infix completion within text fields. This helps when users type words in a different order or start from a middle word.

Example document:

~~~text
The Quick Brown Fox
~~~

A query can start with:

~~~text
brown f
~~~

If exact word order is required, use match_phrase_prefix or match_phrase as appropriate. Phrase-prefix can hit max_expansions limits and is not always the best autocomplete choice.

### 6.5. search_as_you_type Does Not Fix Typos Automatically

If a user types "wireles keybord", bool_prefix will not automatically infer "wireless keyboard". Combine it with fuzzy queries or a dedicated spell correction suggester when needed.

Do not turn on fuzziness on every query by default, as it widens matches and reduces precision.

## 7. Edge N-Gram Analyzer

### 7.1. When Full Control Over Prefix Indexing Is Needed

Edge n-grams are useful when you want explicit control over prefix lengths, analyzers, and fields used for autocomplete.

Example settings:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "autocomplete_edge": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 20
        }
      },
      "analyzer": {
        "autocomplete_index": {
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "autocomplete_edge"
          ]
        },
        "autocomplete_search": {
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "nameAutocomplete": {
        "type": "text",
        "analyzer": "autocomplete_index",
        "search_analyzer": "autocomplete_search"
      }
    }
  }
}
~~~

### 7.2. Why Does the Search Analyzer Differ from the Index Analyzer?

The index analyzer emits multiple prefix tokens. The search analyzer emits normal tokens from the user's input to match those indexed prefixes.

If an edge n-gram analyzer is applied at query time too, short inputs generate unintended tokens and alter query semantics.

### 7.3. Cost of Edge N-Grams

min_gram and max_gram directly affect token counts:

- Setting min_gram too low creates many short prefixes and false positives.
- Setting max_gram too high increases index size.
- Query inputs longer than max_gram may not behave as expected.
- Every analyzer change generally requires a new index and reindexing data.

Measure index size and query latency before enabling edge n-grams across multiple fields.

## 8. Term Suggester for Word-Level Spelling Errors

### 8.1. How Does the Term Suggester Work?

The term suggester proposes replacement words based on edit distance and term statistics within a field. Input is analyzed into tokens, and suggestions are generated per token.

Example:

~~~text
Input: "wirless keybord"
Suggestions:
- wirless -> wireless
- keybord -> keyboard
~~~

The term suggester ignores the main query in the request and does not understand full-sentence context. It is suited for proposing individual word replacements.

### 8.2. Term Suggester Query

Example Query DSL:

~~~json
{
  "suggest": {
    "text": "wirless keybord",
    "spellcheck": {
      "term": {
        "field": "name",
        "suggest_mode": "missing",
        "max_edits": 2,
        "prefix_length": 1,
        "min_word_length": 4,
        "size": 3
      }
    }
  }
}
~~~

Parameters:

- field: field supplying the vocabulary.
- suggest_mode: missing, popular, or always.
- max_edits: maximum edit distance, usually 1 or 2.
- prefix_length: number of leading characters that must match.
- min_word_length: skips short tokens.
- size: number of candidates per token.

### 8.3. suggest_mode

| Mode | Behavior |
|---|---|
| missing | Suggest only when the original token is absent from the index |
| popular | Prefer candidates appearing in more documents than the original token |
| always | Always generate candidates matching edit distance |

missing mode works well for basic spell correction. popular helps when a typo happens to exist in the index, though a much more common word is right. always produces more suggestions but introduces noise.

### 8.4. Limitations of the Term Suggester

The term suggester corrects each token independently. It may suggest a word with small edit distance that does not fit the phrase context.

For example, a valid proper noun or product code may be flagged as a typo. Run the suggester only on appropriate vocabulary fields and verify candidates before presenting them to users.

## 9. Phrase Suggester for Full-Phrase Correction

### 9.1. Why Use the Phrase Suggester?

The phrase suggester builds candidates from term alternatives and ranks whole phrases using an n-gram model. It selects words based on which words co-occur in the indexed data.

Example:

~~~text
Input: "noble prize"
Suggested phrase: "nobel prize"
~~~

A candidate may have a low edit distance yet fail to form a common phrase. The phrase suggester uses co-occurrence statistics to improve choices.

### 9.2. Requires N-Gram-Friendly Mappings

The phrase suggester typically requires a field indexed with a shingle/ngram analyzer. Example mapping:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "trigram_filter": {
          "type": "shingle",
          "min_shingle_size": 2,
          "max_shingle_size": 3,
          "output_unigrams": true
        }
      },
      "analyzer": {
        "trigram_analyzer": {
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "trigram_filter"
          ]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "trigram": {
            "type": "text",
            "analyzer": "trigram_analyzer"
          }
        }
      }
    }
  }
}
~~~

### 9.3. Phrase Suggester Request

~~~json
{
  "suggest": {
    "text": "wirless keybord",
    "phrase-correction": {
      "phrase": {
        "field": "name.trigram",
        "size": 3,
        "gram_size": 3,
        "direct_generator": [
          {
            "field": "name.trigram",
            "suggest_mode": "missing",
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

The phrase suggester can use smoothing models such as stupid_backoff, laplace, or linear_interpolation. Choose based on your corpus and candidate ranking evaluation.

### 9.4. Collate to Verify Phrases Produce Results

The phrase suggester can run a collate query to check whether a candidate phrase actually matches documents. This helps when you only want to suggest corrections that yield results.

Collate executes extra work per candidate, so limit candidate counts and monitor performance. Do not treat collate as an authorization mechanism.

## 10. NativeQuery and Suggester Responses in Spring Data

### 10.1. Attaching a Suggester to NativeQuery

NativeQueryBuilder offers withSuggester, accepting a Suggester from the Elasticsearch Java API Client.

Example suggester construction:

~~~java
Suggester suggester = Suggester.of(s -> s
    .suggesters("spellcheck", field -> field
        .text(input)
        .term(term -> term
            .field("name")
            .size(3)
        )
    )
);

NativeQuery query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

This follows the ELC client builder pattern. If generated methods or overloads differ in your current dependency, consult the Javadoc for that client version. You can use raw Query/Suggester models from the Java API Client when the Spring Data abstraction does not expose a required option.

### 10.2. Extracting Suggestions from SearchHits

Spring Data returns suggest responses on SearchHits:

~~~java
Suggest suggest = hits.getSuggest();

if (suggest != null) {
    var result = suggest.getSuggestion("spellcheck");

    if (result != null) {
        for (var entry : result.getEntries()) {
            for (var option : entry.getOptions()) {
                String candidate = option.getText();
                Double score = option.getScore();
            }
        }
    }
}
~~~

Concrete response types include CompletionSuggestion, TermSuggestion, and PhraseSuggestion. Look up the response using the exact suggestion name declared in the request.

### 10.3. Search and Suggest Can Share a Request

The Search API allows sending both query and suggest in a single request. The application can then:

- Return current search results.
- Return autocomplete or correction suggestions.
- Show corrections only when hit counts are low.
- Display both results and "Did you mean?" when appropriate.

If only suggestions are needed, send a suggest-only request. There is no need to run an extra match_all or dummy query.

### 10.4. Reactive API

ReactiveSearchOperations also supports queries with suggest responses depending on version. You can read ReactiveSearchHits or Suggest from reactive results according to the active interface.

Keep the pipeline reactive and avoid blocking on the request path. If an endpoint only returns a suggestion list, map the response to a small Flux/Mono DTO.

## 11. Context Suggester for Category, Tenant, and Entity Type

### 11.1. Why Use Contexts?

By default, the completion suggester searches every document in the index. An application may need suggestions scoped by:

- Category.
- Brand.
- Tenant.
- Entity type.
- Language.
- Region.

Elasticsearch supports context mappings on completion fields, including category and geo contexts.

### 11.2. Declaring Context Mappings

Spring Data provides the CompletionContext annotation for use with CompletionField. Conceptual example:

~~~java
@CompletionField(
    contexts = {
        @CompletionContext(
            name = "category",
            type = CompletionContext.ContextMappingType.CATEGORY
        )
    }
)
private Completion suggest;
~~~

Exact enum and annotation attributes must match your Spring Data release. Context mappings must be created in the index mapping before indexing completion inputs.

### 11.3. Indexing Contexts Along with Suggestions

A Completion object can carry contexts:

~~~java
Completion completion =
    new Completion(List.of("Wireless Keyboard"));

completion.setContexts(
    Map.of("category", List.of("computer-accessories"))
);

document.setSuggest(completion);
~~~

A context-enabled completion field requires matching contexts at both index time and query time. Omitting the context can cause requests to fail or return unexpected results.

### 11.4. Contexts Do Not Replace Authorization

Contexts filter and boost suggestions by metadata. They do not replace service-level permission checks or Elasticsearch security.

If tenant is a security boundary, derive the tenant context from the authenticated principal. Never accept an arbitrary tenant context from a query string without authorization checks.

## 12. Building an Autocomplete Search API

### 12.1. Bounding Inputs

Before calling Elasticsearch:

- Trim whitespace.
- Normalize Unicode according to product rules.
- Cap input length.
- Skip empty or overly short queries.
- Cap result count.
- Enforce appropriate rate limits.

Do not fire a request on every keystroke without frontend debouncing or API gateway throttling.

### 12.2. Frontend Debouncing

Example UX:

- User types characters.
- Wait roughly 150–300 ms after the last keystroke.
- Send the autocomplete request.
- Cancel the previous in-flight request if a new query is sent.
- Render only the latest response.

Tune the debounce interval based on latency, device type, and user experience. Do not hardcode a number without measuring.

### 12.3. Spring Service

A service can accept a prefix, build the query, and map suggestion responses into DTOs:

~~~java
public List<String> suggestProducts(String prefix) {
    if (prefix == null || prefix.trim().length() < 2) {
        return List.of();
    }

    Suggester suggester = Suggester.of(s -> s
        .suggesters("product-completion", field -> field
            .prefix(prefix.trim())
            .completion(completion -> completion
                .field("suggest")
                .size(8)
                .skipDuplicates(true)
            )
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withSuggester(suggester)
        .build();

    SearchHits<ProductSuggestionDocument> hits =
        operations.search(query, ProductSuggestionDocument.class);

    Suggest suggest = hits.getSuggest();
    if (suggest == null) {
        return List.of();
    }

    var result = suggest.getSuggestion("product-completion");
    if (result == null) {
        return List.of();
    }

    return result.getEntries().stream()
        .flatMap(entry -> entry.getOptions().stream())
        .map(option -> option.getText())
        .distinct()
        .limit(8)
        .toList();
}
~~~

This example targets modern Spring Data/ELC. Check imports and builder overloads against your dependency version. Real applications should return DTOs with ID, label, and suggestion type rather than bare strings.

### 12.4. Never Leak Unauthorized Suggestions

If suggestions come from a multi-tenant catalog or have visibility states, apply matching contexts/filters and verify authorization in the service. Suggestions can leak document names even if the subsequent search endpoint denies opening the document.

### 12.5. Bounded Caching

Popular prefixes can be cached briefly. Cache keys must include tenant, language, category, or other relevant context so suggestions never leak across scopes.

Use short TTLs if the catalog changes frequently. Never store responses containing sensitive data in a shared cache without isolation.

## 13. Building a Spell Correction Flow

### 13.1. Do Not Run Correction on Every Query

A practical strategy:

1. Execute normal search with the original query.
2. If enough relevant results return, return them.
3. If zero hits or low-quality results occur, invoke the term/phrase suggester.
4. Pick candidates with strong relevance.
5. Verify whether the candidate produces search results.
6. Return the suggestion for user confirmation or supply clearly labeled alternative results.

This avoids paying correction overhead on every query.

### 13.2. Correct Only Appropriate Fields

Use text fields with natural vocabulary, such as product name or title. Never use identifier fields, SKUs, phone numbers, or technical codes as a spelling dictionary.

An unfamiliar token could be a valid brand, proper name, or product code. Spell correction must not silently alter critical exact-match values.

### 13.3. Correction Display Thresholds

You can enforce conditions such as:

- Minimum query length.
- Original search returned fewer than a set hit threshold.
- Candidate score exceeds an evaluated threshold.
- Candidate differs meaningfully from the original query.
- Corrected query yields meaningful search results.

Do not pick an arbitrary score threshold and treat it as a true probability. Calibrate thresholds using real query logs.

### 13.4. Preserving the Original Query

An API response might look like:

~~~json
{
  "query": "wirless keybord",
  "suggestedQuery": "wireless keyboard",
  "correctionApplied": false,
  "results": []
}
~~~

If the user clicks the suggestion, record the selected query for analytics. If the application applies correction automatically, clearly show the corrected query and provide an option to revert to the original query.

### 13.5. Dictionaries and Synonyms

Synonyms differ from spell correction:

- Synonyms expand words sharing the same meaning or naming convention.
- Spell correction fixes likely mistyped strings.
- Aliases are intentional alternate names for an entity.

For instance, "laptop" and "notebook" may be synonyms; "keybord" is a typo; "ThinkPad" is a brand/model alias. Do not lump all three into a single mechanism because ranking and maintenance differ.

## 14. Language, Unicode, and Vietnamese

### 14.1. Unicode Normalization

The same character can be encoded using different composed or decomposed Unicode forms. If indexing and querying normalize inconsistently, users may fail to find content even when characters look identical.

Standardize on a normalization form and apply it consistently before both indexing and searching. Do not strip Vietnamese diacritics indiscriminately if the business requires distinguishing accented terms.

### 14.2. Accented and Unaccented Queries

For Vietnamese, users frequently type without diacritics. Strategies include:

- Indexing an unaccented alias.
- Creating a normalized subfield with an appropriate analyzer.
- Providing both accented and unaccented suggestion inputs.
- Using a language-tested normalization service.

Lowercase filters do not strip accents. Use appropriate character filters or asciifolding and test the impact on proper names.

### 14.3. Tokenization

Term and phrase suggesters rely on analyzers. An unsuitable analyzer can mis-segment Vietnamese words, degrading spell correction candidates.

Evaluate analyzers against a real Vietnamese corpus. For multilingual content, split fields by language or select analyzers per document language.

### 14.4. Do Not Fuzzify Codes and Numbers

Fuzzy search on SKUs or model numbers can propose character-close candidates that point to completely different entities.

Use exact keyword matching for identifiers. Enable fuzziness only on natural-language names or fields explicitly vetted for it.

## 15. Ranking Suggestions

### 15.1. Weights in Completion Fields

Completion inputs can carry weights to prioritize popular or important suggestions.

Weights can be derived from:

- Popularity.
- Click-through rate.
- Sales or conversion.
- Active status.
- Business priority.
- Recency, if the use case demands it.

Avoid relying on a single metric if it creates a feedback loop where popular items permanently lock down the top slots.

### 15.2. Deduplication

A product can have multiple aliases that yield identical suggestion text. Use skip_duplicates or deduplicate in the application layer.

Decide whether to merge documents sharing the same label. If two distinct products share a name across different categories, display a secondary label such as brand or category to distinguish them.

### 15.3. Contextual Ranking

You can boost suggestions by category or geo context. For example, queries typed on a phones page can prioritize phone accessories.

Contexts should reflect verified state or trustworthy route/application context.

### 15.4. Do Not Equate Scores Across Suggesters

Completion weights, term suggestion scores, and phrase suggestion scores have completely different scales and semantics. Never merge and sort results from multiple suggesters by comparing raw scores directly without normalization.

If combining multiple sources, build a dedicated ranking layer based on rank position, business priority, and relevance evaluation.

## 16. Spring Data and Elasticsearch Client Versions

### 16.1. NativeQuery and Java API Client

Modern Spring Data Elasticsearch uses NativeQuery with the Elasticsearch Java API Client. NativeQueryBuilder provides withSuggester taking a client Suggester.

Older examples may reference NativeSearchQuery, RestHighLevelClient's SuggestBuilder, or classes under org.elasticsearch. Do not mix those legacy classes with the ELC client.

### 16.2. SearchHits Suggest Response

Spring Data provides SearchHits.getSuggest() along with CompletionSuggestion, TermSuggestion, and PhraseSuggestion since version 4.3. SearchOperations.search(Query, Class) returns both hits and suggest metadata.

Certain older suggest methods returning SearchResponse directly were deprecated in earlier releases. Prefer search(Query, Class) and read getSuggest() according to your release's contract.

### 16.3. Checking the Dependency Tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch,co.elastic.clients:elasticsearch-java,org.elasticsearch.client:*
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration runtimeClasspath
~~~

Let Spring Boot/Spring Data dependency management select the client version. Never override the client version independently just to copy a builder method from external docs.

### 16.4. When Builders Lack a Needed Option

You can invoke the Elasticsearch Java API Client directly with a Suggester or SearchRequest. Reuse the Spring-configured client so endpoints, TLS, and credentials stay consistent.

When calling the client directly, responses deserialize via the transport's JsonpMapper; do not assume custom Spring Data converters run automatically. If complex domain mapping is needed, create a dedicated DTO or adapter.

### 16.5. Server Version Also Governs Features

Completion, search_as_you_type, fuzzy options, contexts, and suggester parameters can vary across Elasticsearch server versions. Consult the reference docs for your exact server major/minor version and run integration tests against a compatible server.

## 17. Testing Autocomplete and Spell Correction

### 17.1. Unit Tests for Normalization and Mapping

Verify:

- Prefixes are trimmed and normalized.
- Null/empty aliases are removed.
- Duplicate inputs are collapsed.
- Weights fall within valid bounds.
- Language and tenant contexts are attached properly.
- Overly short queries do not hit Elasticsearch.

### 17.2. Integration Tests for Completion Suggester

Use real Elasticsearch via Testcontainers:

1. Create the index with a completion mapping.
2. Index documents with varying inputs and weights.
3. Refresh the index.
4. Query a prefix.
5. Verify suggestion texts and ordering.
6. Enable skip_duplicates and confirm duplicates are filtered.
7. Test fuzzy prefix matching with intentional typos.

Do not rely solely on mocked Suggester responses when verifying mappings and fuzzy behavior.

### 17.3. Integration Tests for search_as_you_type

Index multi-word documents and query single-word and multi-word prefixes. Verify:

- Leading prefix matches.
- Middle-word infix matches.
- Bool-prefix queries.
- Category/tenant filters.
- Ranking boosts when words appear in order.

### 17.4. Testing Term and Phrase Suggesters

Create a vocabulary with similar word pairs and sufficiently frequent phrases. Test:

- suggest_mode missing.
- popular/always when applicable.
- max_edits and prefix_length.
- Phrase n-gram fields.
- Candidate collation if used.

Evaluate against a realistic set of typos rather than a single hardcoded example.

### 17.5. Quality Evaluation

Monitor:

- Suggestion acceptance rate.
- Click-through rate.
- Search success after selecting a suggestion.
- Correction acceptance rate.
- False correction rate.
- Empty suggestion rate.
- Latency p50/p95/p99.
- Query volume by prefix length.

Do not optimize solely for clicks, since popular suggestions can earn clicks without helping users complete their tasks.

## 18. Operations and Performance

### 18.1. Limit Result Counts

Autocomplete rarely needs more than a short list. Keep size small and avoid returning entire large documents.

### 18.2. Completion Structures Consume Memory

The completion suggester optimizes for speed by keeping structures in memory. Monitor heap usage, shard sizes, and the number of indexed inputs.

For large indices, review your shard strategy; completion queries spanning many shards incur an extra merge phase across shards. Fewer shards can be faster in some cases, though you should not cram everything into one shard if heap or scale requires sharding.

### 18.3. Search-As-You-Type Adds Subfields

search_as_you_type creates extra shingle and prefix subfields. A higher max_shingle_size improves specific matches at the cost of larger indices.

Start with defaults and raise shingle size only when relevance tests prove it is needed.

### 18.4. Rate Limiting and Abuse Protection

Autocomplete endpoints receive continuous traffic. Apply debouncing, rate limiting, input length caps, and response size caps.

Never allow clients to supply arbitrary analyzers, field names, or suggester configurations.

### 18.5. Observability

Monitor:

- Autocomplete request volume.
- Completion/term/phrase suggester latency.
- Number of returned suggestions.
- Empty result rate.
- Fuzzy correction rate.
- Query errors by mapping/version.
- Memory and search load.
- Suggestion selection rate.

Do not log raw queries if they may contain sensitive data; use sampling or appropriate redaction.

## 19. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Completion query returns nothing | Field not mapped as completion or index not refreshed | Check mapping, documents, and refresh |
| @CompletionField does not create expected mapping | Wrong field type or dependency version | Check Spring Data annotations and actual mapping |
| withSuggester does not compile | NativeQuery/client API version mismatch | Check dependency tree and Javadoc |
| Duplicate suggestions | Multiple documents/aliases share identical text | Use skip_duplicates or deduplicate |
| Fuzzy returns too many results | Prefix too short or edit distance too loose | Increase min length/prefix length, reduce size |
| Completion misses mid-string words | Completion targets prefixes primarily | Use search_as_you_type or another field/index |
| search_as_you_type misses typos | Bool-prefix is not spell correction | Combine with fuzzy or term/phrase suggesters |
| Phrase suggester performs poorly | Missing shingle/ngram mapping | Add trigram field and reindex |
| Term suggester corrupts proper nouns | Dictionary lacks phrase context | Use phrase suggester or exclude field from correction |
| Cross-tenant suggestions appear | Missing context/filter enforcement | Attach authenticated context and enforce authorization |
| Cannot parse suggest response | Reading hits instead of SearchHits.getSuggest | Look up Suggest using the declared name |
| Search endpoint overloaded | Querying every keystroke, large size, or wide fuzzy | Debounce, rate limit, and cap candidates |
| Suggestions stale after rename | Projection out of sync | Update completion inputs via events and verify refresh |
| Unaccented Vietnamese does not match | Lowercase does not strip diacritics | Add tested normalization/aliases |
| Product codes corrected to words | Fuzzy enabled on identifiers | Use exact keyword matching |

## 20. Implementation Workflow

When building autocomplete and spell correction with Spring Data Elasticsearch:

1. Clarify the UX: prefix suggestions, multi-term search-as-you-type, or did-you-mean.
2. Select completion, search_as_you_type, edge n-gram, or a deliberate combination.
3. Design inputs/aliases, weights, and contexts for suggestions.
4. Create mappings with @CompletionField or Search_As_You_Type as appropriate.
5. Index stable inputs and eliminate duplicates.
6. Build NativeQuery with Suggester from the Elasticsearch Java API Client.
7. Read responses via SearchHits.getSuggest() and map to DTOs.
8. Use bounded fuzzy completion for prefix typos.
9. Use term/phrase suggesters for token/phrase correction.
10. Apply language-aware normalization, especially for Unicode and Vietnamese.
11. Enforce tenant/visibility checks before returning suggestions.
12. Cap prefix length, size, debounce interval, and request rate.
13. Run integration tests against a compatible Elasticsearch server.
14. Measure acceptance, false corrections, latency, and resource usage.
15. Update projections whenever names, aliases, popularity, or contexts change.

## 21. Key Takeaways

- Autocomplete completes inputs; spell correction proposes alternative spellings. The two goals require separate mechanisms.
- Completion suggester is optimized for prefix lookups and supports fuzzy options, but it is not a context-aware spell checker.
- search_as_you_type creates shingle/prefix subfields and is typically queried via multi_match bool_prefix.
- Edge n-grams give control over prefix indexing at the expense of more tokens and larger indices.
- Spring Data offers @CompletionField and Completion to map inputs, weights, and contexts.
- NativeQueryBuilder.withSuggester takes a Suggester from the Elasticsearch Java API Client.
- SearchHits.getSuggest() carries suggest responses separately from document hits.
- Term suggester fixes tokens by edit distance without considering query context.
- Phrase suggester ranks whole phrases using n-gram co-occurrence and typically needs shingle mappings.
- Fuzzy completion needs sufficient prefix length and bounded edit distance to avoid noise.
- Context suggesters filter/boost suggestions but never replace authorization.
- For Vietnamese, test Unicode normalization and accented vs. unaccented searches thoroughly.
- Never fuzzify SKUs or identifiers that require exact matching.
- Apply debouncing, size limits, and rate limiting on autocomplete endpoints.
- Track acceptance rates, false corrections, latency, and memory consumption.
- Verify Spring Data and Elasticsearch client versions before copying NativeQuery builder snippets.

A strong search experience often combines completion for quick selections, search_as_you_type for multi-word typing, and phrase/term suggesters to recover from typos when needed. By picking the right mechanism, controlling mappings, and bounding fuzziness, Spring Data Elasticsearch can deliver fast suggestions while preserving accuracy and access control.
