# Distinguishing Autocomplete, Spelling Suggestions, and Prefix Search

In a search box, users can receive three kinds of results that look quite similar on the surface yet solve three different problems:

- **Autocomplete:** suggests complete phrases or data items to choose from when the user has only typed part of a keyword, e.g., typing `iph` and receiving `iPhone 16`.
- **Spell suggestion:** suggests likely correct spellings when the user makes a typo, e.g., `wireles hedphones` returning `wireless headphones`.
- **Prefix search:** finds documents containing a word or value starting with the string the user entered, e.g., `iph` matching `iPhone`.

All three features can appear together on a single search page, but they should not be treated as a single mechanism. In Elasticsearch, autocomplete typically uses Completion Suggester or `search_as_you_type`; spelling suggestion uses Term Suggester or Phrase Suggester; prefix search uses Prefix Query, `match_bool_prefix`, `index_prefixes`, or edge n-gram depending on data structure and ranking needs.

## 1. Quick Comparison of the Three Concepts

| Criterion | Autocomplete | Spell Suggestion | Prefix Search |
|---|---|---|---|
| Question to solve | What might the user want to finish typing? | Which word might the user have misspelled? | Which documents have a term starting with the entered string? |
| Typical input | Prefix being typed: `iph` | Potentially misspelled word/phrase: `iphnoe` | Prefix to search: `iph` |
| Output | List of complete choices | Alternative candidate or corrected phrase | Documents matching the prefix condition |
| Common mechanisms | Completion Suggester, `search_as_you_type`, edge n-gram | Term/Phrase Suggester | Prefix Query, `match_bool_prefix`, edge n-gram |
| Are document search hits needed? | Not necessarily; suggester returns separate options | Not necessarily; suggester returns separate options | Yes, since the goal is finding documents |
| Does it auto-correct the query? | No; only offers choices | Does not rewrite the query unless the application accepts the suggestion | No; only searches documents by prefix |
| UX example | Dropdown “iPhone 16”, “iPhone 16 Pro” | “Did you mean wireless headphones?” | Displays products whose name starts with `iph` |

Suppose the user types `iphnoe`:

1. Prefix search on the exact string `iphnoe` may find no products.
2. Spell suggester may suggest `iphone`.
3. After the user selects `iphone`, autocomplete may offer `iPhone 16`, `iPhone 16 Pro`, or `iPhone case`.

In a real product, you can run spelling suggestions when search results are too few or zero, autocomplete as input changes, and prefix search to retrieve documents matching what the user is typing.

## 2. Autocomplete with Completion Suggester

Completion Suggester is specifically designed for autocomplete. Elasticsearch indexes inputs into a data structure optimized for prefix lookup. When the user enters a prefix, the suggester returns matching complete inputs.

Example list of indexed inputs:

```text
iPhone 16
iPhone 16 Pro
iPhone 16 Pro Max
iPhone case
Wireless headphones
Wireless keyboard
```

When receiving the prefix `iph`, Completion Suggester can return options starting with that prefix. The result consists of suggestion options, not a list of document hits found by an ordinary query.

### `completion` Field Mapping

A field used for Completion Suggester must have a `completion` mapping type:

```http
PUT /products
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
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
}
```

`completion` is a dedicated field type; you cannot substitute a regular `text` field and expect Completion Suggester to work. `analyzer` and `search_analyzer` determine how inputs are normalized at index time and when looking up suggestions. `max_input_length` caps the length of each indexed input.

### Indexing Suggestion Values

A single document can store multiple inputs for the same item:

```http
PUT /products/_doc/p-1001
Content-Type: application/json

{
  "name": "Apple iPhone 16 Pro",
  "suggest": [
    "iPhone 16 Pro",
    "Apple iPhone 16 Pro",
    "iPhone Pro"
  ]
}
```

A completion field can accept a string, an array of strings, or an input structure with weight/context depending on configuration. Including multiple ways to refer to an item helps users find the same product across different starting words.

### Autocomplete Query

```http
POST /products/_search
Content-Type: application/json

{
  "_source": ["name"],
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

`prefix` is what the user is typing; `size` limits the number of suggestions; `skip_duplicates` removes options with duplicate text. The response appears under `suggest.product_autocomplete`, where each option can contain text, score, and related document information.

### Advantages and Limitations

**Advantages:** low latency for prefix lookups, ideal for autocomplete dropdowns, supports weight and context completion.

**Limitations:** requires a separate `completion` field; inputs must be prepared and indexed; not a full-text search engine replacing ordinary queries; does not automatically fix typos; the completion structure has a memory footprint that must be monitored.

## 3. Using Completion Suggester in Spring Data Elasticsearch

Spring Data Elasticsearch provides `@CompletionField` and the `Completion` type to map completion fields.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;

    @CompletionField(maxInputLength = 100)
    private Completion suggest;

    // Constructors, getters and setters
}
```

When creating a document:

```java
product.setSuggest(new Completion(new String[] {
    "iPhone 16 Pro",
    "Apple iPhone 16 Pro",
    "iPhone Pro"
}));
```

`NativeQuery` can carry a suggester built with the Elasticsearch Java API Client:

```java
import co.elastic.clients.elasticsearch.core.search.FieldSuggester;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

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

Execute and read results:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasSuggest()) {
    Suggest suggest = results.getSuggest();
    Suggest.Suggestion<?> completion =
        suggest.getSuggestion("product_autocomplete");

    if (completion != null) {
        for (Suggest.Suggestion.Entry<?> entry : completion.getEntries()) {
            for (Suggest.Suggestion.Entry.Option option : entry.getOptions()) {
                String text = option.getText();
                // Add text to the autocomplete choice list.
            }
        }
    }
}
```

Builder classes of the Elasticsearch Java API Client are generated per the client version used by Spring Data. If method names or option types differ in your project's dependencies, use the API matching that version; do not mix imports from the legacy `RestHighLevelClient` with ELC.

## 4. Context Completion: Categorized Autocomplete

Context completion lets you filter or boost suggestions based on context, such as product category, tenant, language, or location.

For example, the user types `iph` inside the `phones` category. The system wants to suggest phones and avoid showing accessories with a similar prefix.

Example mapping:

```json
{
  "properties": {
    "suggest": {
      "type": "completion",
      "contexts": [
        {
          "name": "category",
          "type": "category"
        }
      ]
    }
  }
}
```

Indexing a document with context:

```json
{
  "suggest": {
    "input": ["iPhone 16 Pro", "Apple iPhone 16 Pro"],
    "contexts": {
      "category": ["phones"]
    }
  }
}
```

Query retrieving only suggestions belonging to category `phones`:

```json
{
  "suggest": {
    "product_autocomplete": {
      "prefix": "iph",
      "completion": {
        "field": "suggest",
        "size": 5,
        "contexts": {
          "category": ["phones"]
        }
      }
    }
  }
}
```

Contexts must be defined in the mapping and sent consistently at both index time and query time. Context completion can filter or boost by context; choose the behavior fitting your goal. If contexts are not indexed properly, queries may return no results even when the prefix exists.

## 5. Autocomplete with `search_as_you_type`

Completion Suggester is not the only option for autocomplete. If you want autocomplete based on multi-word content, you can use a `search_as_you_type` field combined with `multi_match` using `bool_prefix`.

`search_as_you_type` creates subfields supporting word-order matching and prefix matching on the last word. Example mapping:

```http
PUT /products
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "search_as_you_type"
      }
    }
  }
}
```

Elasticsearch automatically creates subfields such as:

- `name`: the root field.
- `name._2gram`: supports adjacent two-token phrases.
- `name._3gram`: supports adjacent three-token phrases.
- `name._index_prefix`: prefix structure used for matching queries.

Query:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "multi_match": {
      "query": "wireless head",
      "type": "bool_prefix",
      "fields": [
        "name",
        "name._2gram",
        "name._3gram"
      ]
    }
  }
}
```

`bool_prefix` searches already-entered tokens as matches and treats the last token as a prefix. It fits when the user types multiple words, such as `wireless head`, and wants to find `Wireless Headphones`. The query still returns document hits and can rank them by score.

### When to Choose `search_as_you_type`?

- Searching across multiple words where word order matters.
- Wanting document relevance scores.
- Wanting to leverage subfields automatically created by Elasticsearch.
- Needing a “search as you type” experience on titles or product names.

### When Not to Choose It?

- Only needing a very fast prefix suggestion list with weights/contexts: Completion Suggester is usually a better fit.
- Needing spelling correction: use Term/Phrase Suggester.
- Needing exact string-start prefix matching on a code: Prefix Query on `keyword` can be simpler.

## 6. Prefix Search with Prefix Query

Prefix Query finds terms whose value starts with a specified prefix. It suits codes, identifiers, or `keyword` fields needing prefix matching.

Example `sku` field mapped as `keyword`:

```json
{
  "properties": {
    "sku": {
      "type": "keyword"
    }
  }
}
```

Query finding SKUs starting with `IPH`:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "prefix": {
      "sku": {
        "value": "IPH"
      }
    }
  }
}
```

If `sku` is `keyword`, the search typically evaluates the entire term value. It suits product codes, customer IDs, or identifiers with clear normalization rules.

### Prefix Query Is Not a Full-Text Query

Prefix Query does not automatically split sentences into words like `match`. If a field is `text`, the query operates on terms generated by the analyzer rather than comparing against the raw `_source` string. For example, a prefix may match the last token or any analyzed token depending on the analyzer and indexed data. If you want to search across multiple words with an incomplete last token, `match_bool_prefix` or `search_as_you_type` is usually easier to control.

### Prefix Query in Spring Data `NativeQuery`

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

String prefix = "IPH";

Query query = NativeQuery.builder()
    .withQuery(q -> q.prefix(p -> p
        .field("sku")
        .value(prefix)
    ))
    .build();
```

Execute via `ElasticsearchOperations.search(...)` to obtain `SearchHits<ProductDocument>`. Because this is a document-finding query, results reside in hits, unlike completion suggestion options.

## 7. Optimizing Prefix Query with `index_prefixes`

Prefix Query on high-cardinality fields or highly variable short/long prefixes can be resource-intensive without supporting index structures. On `text` fields, you can enable `index_prefixes` so Elasticsearch indexes prefixes within a specified length range.

```json
{
  "properties": {
    "title": {
      "type": "text",
      "index_prefixes": {
        "min_chars": 2,
        "max_chars": 10
      }
    }
  }
}
```

Elasticsearch creates an internal field supporting prefix queries for prefix lengths in the configured range. This can improve prefix lookup performance at the cost of increased indexing overhead and storage.

`index_prefixes` fits when you still want prefix-style queries on `text` fields and can bound common prefix lengths upfront. If multi-token autocomplete is needed, `search_as_you_type` may express the goal better.

## 8. Prefix Matching with Edge N-gram

Edge n-gram is an analyzer technique that generates sub-tokens starting from the beginning of the original token. For example, the token `wireless` can produce:

```text
wi
wir
wire
wirel
wirele
wireles
wireless
```

When the user types `wirel`, the query analyzer produces token `wirel` and finds documents containing the matching prefix token. This technique is useful for autocomplete on `text` fields and allows combining with ordinary query scoring.

### Configuring an Edge N-gram Analyzer

```http
PUT /products
Content-Type: application/json

{
  "settings": {
    "analysis": {
      "filter": {
        "name_edge_ngram": {
          "type": "edge_ngram",
          "min_gram": 2,
          "max_gram": 15
        }
      },
      "analyzer": {
        "name_index_analyzer": {
          "tokenizer": "standard",
          "filter": ["lowercase", "name_edge_ngram"]
        },
        "name_search_analyzer": {
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "name_index_analyzer",
        "search_analyzer": "name_search_analyzer"
      }
    }
  }
}
```

The index-time analyzer generates prefix tokens; the search analyzer only normalizes input into regular tokens. Do not unintentionally use an edge n-gram analyzer on both sides, as it can expand the query into unwanted prefixes.

### Advantages and Costs

- Ordinary full-text queries can be used on fields with prefix tokens.
- Easy to combine with scoring, filters, and multiple fields.
- Increases the number of indexed tokens, increasing storage and indexing cost.
- Requires choosing appropriate `min_gram`/`max_gram`; overly short prefixes can produce noisy results.
- Changing analyzers usually requires creating a new index and reindexing data.

Edge n-gram is not spelling correction. If the user mistypes a character, the misspelled prefix token still will not match the correct token.

## 9. Multi-Word Prefix Search with `match_bool_prefix`

`match_bool_prefix` analyzes the input into tokens. Tokens before the last one are searched as term matches, while the last token is treated as a prefix. This is convenient when the user is mid-way through typing the final word in a phrase.

Example:

```http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match_bool_prefix": {
      "name": "wireless head"
    }
  }
}
```

With an analyzer producing tokens `wireless` and `head`, the query finds documents containing matching terms for `wireless` and a token starting with `head`, such as `headphones`.

In Spring Data Elasticsearch:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.matchBoolPrefix(m -> m
        .field("name")
        .query("wireless head")
    ))
    .build();
```

`match_bool_prefix` returns document hits with scoring. It differs from Completion Suggester in that its goal is finding documents matching the phrase being typed, not looking up a separately indexed list of autocomplete inputs.

## 10. Spell Suggestions with Term Suggester

Term Suggester proposes replacement candidates for individual tokens based on edit distance and field vocabulary statistics. For example, `elastcsearch` can be suggested as `elasticsearch`.

Request:

```http
POST /products/_search
Content-Type: application/json

{
  "suggest": {
    "product_terms": {
      "text": "wireles hedphones",
      "term": {
        "field": "name",
        "suggest_mode": "popular",
        "max_edits": 2,
        "size": 5
      }
    }
  }
}
```

Term suggester produces suggestions at the token level. For multi-word inputs, the response can contain separate entries per token. The application must decide how to display or combine candidates; it does not automatically produce a single contextually sound corrected sentence.

Selected options:

- `suggest_mode: missing`: only suggests when the token does not exist in the vocabulary.
- `suggest_mode: popular`: prefers candidates more common than the input token.
- `suggest_mode: always`: always considers candidates.
- `max_edits`: limits allowed edit distance, typically 1 or 2.
- `size`: maximum number of candidates per entry.
- `prefix_length`: number of leading characters that must match before considering edit distance.

Term suggester does not fully understand sentence meaning. It can suggest individual words without recognizing which phrase makes sense in context. For phrase-level corrections, consider Phrase Suggester.

## 11. Phrase-Level Spell Suggestions with Phrase Suggester

Phrase Suggester uses candidate generators and phrase statistics (often based on shingles/n-grams) to rank full-phrase corrections. It fits better when typos occur inside a multi-word sentence or name.

Example mapping with a trigram field:

```json
{
  "settings": {
    "analysis": {
      "filter": {
        "name_shingle": {
          "type": "shingle",
          "min_shingle_size": 2,
          "max_shingle_size": 3
        }
      },
      "analyzer": {
        "name_trigram": {
          "tokenizer": "standard",
          "filter": ["lowercase", "name_shingle"]
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
            "analyzer": "name_trigram"
          }
        }
      }
    }
  }
}
```

Phrase suggester query:

```http
POST /products/_search
Content-Type: application/json

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
            "suggest_mode": "always",
            "max_edits": 2
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
```

Phrase Suggester evaluates candidates using n-gram statistics and produces more plausible phrases. Quality depends on indexed data, analyzer, shingle field, and candidate generators. With a small catalog or sparse language data, suggestions may be poor even when the query succeeds.

## 12. Reading Term/Phrase Suggestions in Spring Data

`NativeQuery` can attach a suggester via `withSuggester(...)`, just like Completion Suggester, while choosing the `term` or `phrase` type:

```java
import co.elastic.clients.elasticsearch.core.search.FieldSuggester;
import co.elastic.clients.elasticsearch.core.search.Suggester;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Suggester suggester = Suggester.of(s -> s
    .text("wireles hedphones")
    .suggesters("product_terms", FieldSuggester.of(fs -> fs
        .term(t -> t
            .field("name")
            .suggestMode(co.elastic.clients.elasticsearch._types.SuggestMode.Popular)
            .size(5)
        )
    ))
);

Query query = NativeQuery.builder()
    .withSuggester(suggester)
    .build();
```

Reading results from `SearchHits.getSuggest()`:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductDocument> results =
    operations.search(query, ProductDocument.class);

if (results.hasSuggest()) {
    Suggest suggest = results.getSuggest();
    Suggest.Suggestion<?> termSuggestion =
        suggest.getSuggestion("product_terms");

    if (termSuggestion != null) {
        for (Suggest.Suggestion.Entry<?> entry : termSuggestion.getEntries()) {
            String original = entry.getText();

            for (Suggest.Suggestion.Entry.Option option : entry.getOptions()) {
                String candidate = option.getText();
                // For example: display candidate as a spell suggestion.
            }
        }
    }
}
```

Term suggestions usually have entries per token and options per candidate. Phrase suggestions have corresponding entry/option types where the option text represents the suggested phrase. Check the exact suggester type and response type when reading specialized metadata such as score or frequency.

## 13. When to Use Prefix Query, `match_bool_prefix`, or `search_as_you_type`?

All three approaches can support search while the user is typing, but their semantics differ.

| Mechanism | Suitable For | Example Input | Desired Outcome |
|---|---|---|---|
| Prefix Query on `keyword` | Codes or raw values starting with a prefix | `IPH` | SKUs starting with `IPH` |
| Prefix Query on `text` | Prefix of an analyzer-indexed token | `head` | Documents with a token starting with `head` |
| `match_bool_prefix` | Multi-word phrase, incomplete final token | `wireless head` | Find documents with `wireless` and a prefix token `head` |
| `search_as_you_type` + `bool_prefix` | Multi-word search-as-you-type with good relevance | `wireless head` | Find and rank matching products |
| Edge n-gram | Autocomplete/prefix matching via n-grammed tokens | `wirel` | Documents containing indexed prefix tokens |
| Completion Suggester | Dropdown suggesting complete inputs | `wirel` | Indexed inputs starting with the prefix |

If you only need to filter codes, Prefix Query on `keyword` is usually the simplest approach. If you need multi-word search while typing, `search_as_you_type` or `match_bool_prefix` is usually a better fit. If the UI needs a curated list of choices, Completion Suggester is typically appropriate.

## 14. Choosing Analyzers and Case Normalization

Autocomplete and prefix search rely on inputs at index time and search time being normalized compatibly.

Suppose the user types `IPH`, while the indexed data is `iPhone`. If a `keyword` field preserves case, Prefix Query may not match as desired. You can normalize data before indexing and querying, or use a normalizer on the keyword field when appropriate.

Example keyword normalizer:

```json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "sku": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
```

Normalizers enable case-insensitive matching and can strip diacritics via configured filters. Make sure stripping diacritics is appropriate for identifiers or the language; do not automatically strip diacritics if doing so collapses two distinct business values into one.

For text fields, analyzers can lowercase, tokenize, or apply synonyms. Use `_analyze` to inspect tokens:

```http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Headphones"
}
```

If query and index analyzers are incompatible, prefix or spelling suggestions may miss results that users expect.

## 15. Which Tokens Can Prefix Search Match?

Prefix search on `keyword` compares against the entire term. On `text`, an analyzer can produce multiple tokens from one sentence.

For example, `name = "Wireless Headphones Pro"` after using the standard analyzer may produce tokens:

```text
wireless
headphones
pro
```

A Prefix Query on `name` with `head` can match the token `headphones`, even though `head` is not a prefix of the entire `_source` string from the first character. This searches prefixes of indexed tokens, not prefixes of the entire original sentence.

If the requirement is matching from the first character of the whole value, use a normalized `keyword` field. If the requirement is matching the final incomplete token in a sentence being typed, use `match_bool_prefix` or `search_as_you_type`.

## 16. Ranking Autocomplete and Prefix Search Results

Autocomplete may need ranking by popularity, priority, or context. Completion inputs can carry a `weight` so prominent choices rank higher.

Example indexing a completion input with weight:

```json
{
  "suggest": {
    "input": ["iPhone 16 Pro"],
    "weight": 10
  }
}
```

A popular choice can have a higher weight than a less-used one. Weight is a suggestion ranking signal, not the probability a user will pick it.

With `search_as_you_type` or prefix queries returning hits, ordering usually relies on `_score` if the query scores documents. You can combine field boosts, popularity, or recency as needed. With prefix queries on keyword fields, relevance scores may not sufficiently differentiate values; the application can sort by a business field.

Do not mix results from Completion Suggester and search hits into a single uncategorized list if their scores are on different scales. If combining them, normalize via application ranking rules or keep them in two separate UI groups.

## 17. Designing a Search Experience Combining All Three Features

A search flow can operate as follows:

```text
User types characters
        |
        v
Short input / prefix being typed
        |
        +----> Autocomplete
        |       Completion Suggester or search_as_you_type
        |       Returns complete choices
        |
        v
User submits query
        |
        v
Full-text / prefix search
        |
        +----> Has results: display document hits
        |
        +----> Zero or too few results:
                 run Term/Phrase Suggester
                 display “Did you mean...”
```

### UI Behavior Tips

- Debounce input to avoid sending requests on every keystroke at excessive frequency.
- Only trigger autocomplete once input reaches a minimum length, such as 2 characters.
- Limit suggestion count, typically around 5–10 choices depending on the UI.
- When the user picks a suggestion, replace the input with the selected phrase and run a normal search.
- Run spelling suggestions when results are empty or low quality, rather than on every keystroke.
- Show spell suggestions as an option; do not silently rewrite the user's query unless UX rules clearly specify it.
- Use prefix search for codes or token prefixes when that is the semantics users expect.

## 18. Comparing Index and Query Costs

| Mechanism | Index Cost | Query Cost | Notes |
|---|---|---|---|
| Completion Suggester | Builds dedicated completion structure; can increase heap usage | Fast prefix lookup | Monitor input count and completion field size |
| Term/Phrase Suggester | Relies on field and vocabulary statistics; phrase usually needs shingle field | Depends on candidate generation and statistics | Run only when word correction is needed; quality depends on corpus |
| Prefix Query on keyword | Low if indexing only keyword | Can be costlier if prefix lookup is broad and field unoptimized | Use `index_prefixes` for some text cases |
| `search_as_you_type` | Creates multiple extra subfields/tokens | Optimized for search-as-you-type | Larger footprint than a single text field |
| Edge n-gram | Increases indexed token count significantly | Regular token queries can be fast | Choose min/max gram and analyzer carefully |
| `match_bool_prefix` | Depends on existing text mapping | Full-text query with prefix on last token | Easy to combine relevance and multiple fields |

No single mechanism wins in every scenario. Choose based on UX, data structure, input volume, ranking needs, latency, and storage cost.

## 19. Common Pitfalls

### Using Completion Suggester for Spelling Correction

Completion only finds inputs matching a prefix. It does not automatically find words with close edit distance. Use Term/Phrase Suggester if spelling suggestions are needed.

### Using Prefix Query to Fix Typos

Prefix Query only matches term prefixes. `iphnoe` will not automatically match `iphone` just because the two words are close. Use a spelling suggester or appropriate fuzzy mechanism.

### Using Prefix Query on `text` Expecting a Match from the Start of `_source`

`text` fields are tokenized by an analyzer. Prefix Query can match the prefix of any token per the index structure. Use a `keyword` field if you need prefixes of the full value.

### Mapping Completion as `text`

Completion Suggester requires a `completion` field type. An analyzed text field does not automatically act as a completion field.

### Inconsistent Case Normalization

Differing index and query analyzers/normalizers can prevent prefixes from matching. Inspect `_analyze` and field normalizers.

### Using Edge N-gram with Too Large a `max_gram`

Every token generates many sub-tokens, inflating index size and indexing cost. Choose gram ranges based on common input lengths.

### Calling Spelling Suggestions on Every Keystroke

Term/Phrase Suggester can be more expensive than simple prefix autocomplete. Trigger it conditionally on UX states such as zero results or user correction requests.

### Auto-Rewriting Queries Without Notification

Suggestions are only candidates. If the application silently alters input, users may get results different from what they typed. Display options and let the user decide.

## 20. Testing the Three Mechanisms Separately

Create a dataset covering these cases:

| Indexed Data | Input | Expected Test Result |
|---|---|---|
| `iPhone 16 Pro` in completion field | `iph` | Completion returns choice `iPhone 16 Pro` |
| `Wireless Headphones` in text field | `wireless head` | `match_bool_prefix`/`search_as_you_type` finds the document |
| `IPH-1001` in keyword SKU | `IPH` | Prefix Query finds the document |
| `Elasticsearch` in vocabulary field | `elastcsearch` | Term suggester can suggest `elasticsearch` |
| `Wireless Headphones` in shingle field | `wireles hedphones` | Phrase suggester can suggest the close phrase |
| `iPhone 16` with category context `phones` | `iph`, context `phones` | Context completion returns choices in the matching category |

Also test:

- Case variations and Vietnamese diacritics.
- Prefixes shorter than `min_gram` or longer than `max_gram`.
- Empty strings and whitespace-only inputs.
- Multiple documents sharing the same suggestion text.
- Different weights and context filters.
- Documents lacking a completion field or with missing fields.
- Spelling candidates with different meanings but close edit distance.
- Multi-word queries with an incomplete final token.

Evaluate quality with real query sets and suggestion click-through rates. Simply verifying a query runs without errors is not enough to conclude autocomplete or spelling suggestions are useful.

## 21. Workflow for Choosing a Solution

When implementing suggestion features for a search box, identify the goal first:

1. If you want to suggest complete names/items from a prefix, use Completion Suggester.
2. If you need multi-word autocomplete with document relevance, use `search_as_you_type` and `bool_prefix`.
3. If you need to match codes or raw values starting with a prefix, use Prefix Query on a normalized `keyword`.
4. If you need prefix lookup on text tokens, consider Prefix Query with `index_prefixes` or edge n-gram.
5. If you want to fix a single misspelled token, use Term Suggester.
6. If you want to suggest corrections for an entire phrase, use Phrase Suggester with a suitable shingle field.
7. Define analyzer/normalizer, result limits, input length, and ranking rules.
8. Test each mechanism independently with valid queries, typos, multi-word prefixes, and boundary values.
9. Set up debounce and suggestion trigger conditions in the application layer.
10. Monitor latency, suggestion selection rate, index size, and result quality.

## 22. Conclusion

Autocomplete, spelling suggestion, and prefix search serve three distinct needs. Completion Suggester returns complete inputs matching a prefix and fits dropdown suggestions. Term/Phrase Suggester produces spelling correction candidates at the word or phrase level. Prefix Query, `match_bool_prefix`, `search_as_you_type`, and edge n-gram find documents containing terms or tokens starting with what the user entered.

In Spring Data Elasticsearch, Completion Suggester can use `@CompletionField`, `Completion`, and `NativeQuery.withSuggester(...)`; spelling suggesters are likewise declared via `Suggester`; prefix search uses `NativeQuery` with `prefix` or `matchBoolPrefix`. Choose mappings aligned with your goals, normalize inputs consistently, and distinguish suggestion options from document search hits. When all three features are implemented in their proper roles, a search interface can provide fast suggestions, handle typos, and retrieve documents by prefix without conflating the semantics of each result.

## References

- [Elasticsearch – Search suggesters](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters)
- [Elasticsearch – Completion suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#completion-suggester)
- [Elasticsearch – Term suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#term-suggester)
- [Elasticsearch – Phrase suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#phrase-suggester)
- [Elasticsearch – Prefix query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-prefix-query)
- [Elasticsearch – Match bool prefix query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-match-bool-prefix-query)
- [Elasticsearch – Search as you type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/search-as-you-type)
- [Elasticsearch – Edge n-gram token filter](https://www.elastic.co/docs/reference/text-analysis/analysis-edgengram-tokenfilter)
- [Spring Data Elasticsearch – NativeQuery and search operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
