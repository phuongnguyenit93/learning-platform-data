# Analyzer, tokenizer, token filter, and normalizer

## 1. Why does Elasticsearch need text analysis?

When a user enters a search phrase, Elasticsearch needs to convert the text into a form that can be indexed and matched efficiently. That process is called **analysis**. It typically splits sentences into tokens, normalizes uppercase and lowercase letters, handles punctuation, removes unnecessary words, or reduces words to their root forms.

For example, a document has the title:

~~~text
The Quick Brown Foxes!
~~~

It can be analyzed into the tokens:

~~~text
quick
brown
fox
~~~

This is only an illustrative example of a configuration that handles lowercasing and stemming. Actual output depends on the configured analyzer, tokenizer, and token filters.

Without text analysis, search would often require matching the entire string or manually handling many variations. Analysis enables Elasticsearch to find relevant content even when the document text and the query differ in casing, punctuation, or word form.

In Elasticsearch, analysis is primarily used for `text` fields. `keyword` fields usually store the entire value as a single unit for filtering, sorting, or grouping; these fields can use a **normalizer** to normalize values while keeping them as a single token.

## 2. What components make up an analysis chain?

A complete analyzer can consist of three steps in order:

~~~text
Input text
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
Output token list
~~~

- **Character filter** processes text before tokenization, such as stripping HTML tags or replacing a character sequence.
- **Tokenizer** splits text into tokens according to specific rules.
- **Token filter** takes the token list and modifies, removes, or adds tokens.

An analyzer can have zero, one, or multiple character filters; it has exactly one tokenizer and can have multiple token filters. The order of filters is critical because each step receives the output of the previous step.

For example, given `"<p>CAFÉ Shoes</p>"`, an analyzer can strip HTML tags, split into tokens, lowercase, and convert accented characters to ASCII. The result could be `cafe` and `shoes`.

## 3. Character filter: processing characters before tokenization

A character filter receives the entire input string and transforms it before the tokenizer runs. Elasticsearch provides several commonly used types:

| Character filter | Purpose | Example usage |
|---|---|---|
| `html_strip` | Strips HTML tags and decodes certain HTML entities | Remove `<b>` from description text |
| `mapping` | Replaces strings or characters based on a mapping table | Replace special symbols or normalize character variants |
| `pattern_replace` | Replaces segments matching a regular expression | Strip formatting codes or replace delimiters |

For example, `html_strip` can turn:

~~~html
<p>Spring <strong>Data</strong></p>
~~~

into the text:

~~~text
Spring Data
~~~

An analyzer configuration with a character filter:

~~~json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "remove_html": {
          "type": "html_strip"
        }
      },
      "analyzer": {
        "html_text": {
          "type": "custom",
          "char_filter": ["remove_html"],
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  }
}
~~~

Character filters must also be weighed carefully when processing formatted content. For example, removing all hyphens might alter the meaning of certain product codes or terms. Only replace characters that your application's search rules truly intend to normalize.

## 4. Tokenizer: splitting text into tokens

A tokenizer determines the boundaries between tokens. It is the only required component in a custom analyzer. Elasticsearch provides many built-in tokenizers:

| Tokenizer | How it works | Common cases |
|---|---|---|
| `standard` | Splits text according to Unicode word boundary rules | General text, multiple languages |
| `whitespace` | Splits on whitespace | Data with already normalized word boundaries |
| `letter` | Splits on non-letter characters | Content consisting primarily of words |
| `keyword` | Keeps the entire input as a single token | When the whole string must be treated as one unit |
| `pattern` | Splits according to a regular expression | Data with custom delimiters |
| `ngram` | Generates substrings of configured lengths | Partial string search |
| `edge_ngram` | Generates substrings from the beginning of tokens | As-you-type search suggestions |
| `path_hierarchy` | Splits paths into hierarchical levels from left to right | Filtering by directory tree or hierarchy |

For example, with the `standard` tokenizer, the string:

~~~text
Spring Data Elasticsearch 2026
~~~

can be split into tokens corresponding to `Spring`, `Data`, `Elasticsearch`, and `2026`. Subsequent token filters can then convert these tokens to lowercase.

With the `keyword` tokenizer, the entire string `Spring Data Elasticsearch 2026` becomes a single token. Thus, this tokenizer is suitable when the entire value must be treated as one unit. On `keyword` fields, Elasticsearch typically uses this mechanism via the keyword analyzer or a normalizer.

### N-gram and edge n-gram

`ngram` creates multiple consecutive substrings from the original token. For instance, with the word `phone` and n-gram lengths from 2 to 3, the tokens may include `ph`, `pho`, `ho`, `hon`, `on`, and `one`.

`edge_ngram` only creates substrings starting from the beginning of the token. With the same word `phone`, the result may include `ph`, `pho`, `phon`, and `phone` depending on length limits.

These two tokenizers are useful for partial matching and autocomplete, but they increase the number of indexed tokens. Limit the length range, use a dedicated field for suggestions, and measure index size before broad rollout.

### Considerations for Vietnamese

Vietnamese writes syllables separated by spaces, while a word can consist of multiple syllables. Tokenizers based on whitespace or Unicode word boundaries may split individual syllables, without necessarily recognizing compound word boundaries linguistically. For example, a multi-syllable phrase may be split into multiple tokens even though a reader considers it a single lexical unit.

Therefore, default analyzers may suffice for basic search but might not meet high-quality Vietnamese search requirements. If you need compound word recognition, synonyms, or language variants, evaluate appropriate analysis plugins, dictionaries, or dedicated preprocessing steps. Stripping diacritics with `asciifolding` is only character normalization; it does not perform Vietnamese word segmentation.

## 5. Token filter: transforming the token list

A token filter receives the tokens produced by the tokenizer. Multiple filters can be chained sequentially to achieve the desired analysis rules.

Commonly used token filters:

| Token filter | Effect | Example or purpose |
|---|---|---|
| `lowercase` | Converts tokens to lowercase | `Spring` to `spring` |
| `uppercase` | Converts tokens to uppercase | Normalize codes to uppercase |
| `asciifolding` | Converts many non-ASCII characters to ASCII equivalents | `café` to `cafe` |
| `stop` | Removes stop words based on a list | Omit overly common words when appropriate |
| `stemmer` | Reduces words to an approximate root form by language | `running` can become `run` |
| `synonym` / `synonym_graph` | Expands or replaces tokens with synonyms | Find `tv` alongside `television` |
| `trim` | Trims leading and trailing whitespace from tokens | Clean up tokens |
| `unique` | Removes duplicate tokens | Limit duplicates within a position |
| `ngram` / `edge_ngram` | Generates sub-tokens from already split tokens | Partial search or autocomplete |
| `shingle` | Creates tokens from groups of adjacent tokens | Improve phrase matching capability |

### Filter order affects results

Suppose an analyzer uses `lowercase` and `stop`. The `stop` token filter removes stop words based on a configured list. Lowercasing first ensures the stopword list applies consistently across capitalized variants.

Similarly, when using a synonym filter, consider how synonyms themselves are analyzed. A synonym phrase may contain multiple words; `synonym_graph` is usually better suited for multi-word queries because it preserves the token relationship metadata needed for phrase queries. Synonym configuration should also be tested alongside preceding filters.

Do not add every filter just because it is available. Stemming can erase semantic distinctions in certain domains; stopwords might include business-critical terms; synonyms can increase unwanted matches. Define the required search behavior before choosing the filter chain.

## 6. Built-in analyzers and custom analyzers

Elasticsearch provides many built-in analyzers. Popular choices include:

| Analyzer | Key characteristics | When to consider |
|---|---|---|
| `standard` | Standard tokenizer and lowercase; default stopword config removes no words | Starting point for general text |
| `simple` | Splits on non-letter characters and lowercases | Text composed primarily of letters |
| `whitespace` | Splits on whitespace | When word boundaries are already controlled |
| `stop` | Similar to simple plus stopword removal | When language-specific stopwords must be dropped |
| `keyword` | Keeps the entire string as a single token | Values needing whole-string matching |
| `pattern` | Splits using a regular expression | Data with custom delimiter structures |
| `language` | Applies analysis rules for a supported language | Text in the corresponding language |
| `fingerprint` | Normalizes and sorts tokens to build a fingerprint representation | Identifying token-equivalent content |

When built-in analyzers do not meet requirements, you can define a **custom analyzer** by combining character filters, a tokenizer, and token filters.

Example custom analyzer for product names:

~~~json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "strip_html": {
          "type": "html_strip"
        }
      },
      "filter": {
        "fold_accents": {
          "type": "asciifolding",
          "preserve_original": true
        }
      },
      "analyzer": {
        "product_index": {
          "type": "custom",
          "char_filter": ["strip_html"],
          "tokenizer": "standard",
          "filter": ["lowercase", "fold_accents"]
        },
        "product_search": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "fold_accents"]
        }
      }
    }
  }
}
~~~

The `product_index` analyzer strips HTML tags, splits words, lowercases, and folds accents. `product_search` applies matching normalization to query input. In this configuration, `preserve_original` keeps both the original token and the folded token; this can increase token count and should be validated against expected results.

Analyzer configurations must be declared in the index settings before creating a mapping that uses them. If an index already exists, simply editing a config file or Java annotation does not automatically modify the analyzer stored in the index.

## 7. Index-time and search-time analyzers

Elasticsearch can analyze text at two points:

- **Index time:** analyzes field values before storing tokens in the inverted index.
- **Search time:** analyzes the query string before matching against indexed tokens.

In the mapping, you can specify `analyzer` for indexing and `search_analyzer` for querying. If `search_analyzer` is omitted, the field's analyzer is typically used as the default for searching.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "product_index",
        "search_analyzer": "product_search"
      }
    }
  }
}
~~~

The two analyzers do not have to be identical. However, they must produce compatible tokens. If stemming is used at index time but not at search time, queries may produce tokens that fail to match stored tokens. Conversely, if the search analyzer expands too many synonyms, results may be broader than intended.

A common approach is keeping the index analyzer stable while adjusting the search analyzer for needs such as synonyms or query handling. The choice also depends on configuration flexibility and application consistency requirements.

## 8. Normalizer: normalizing keyword values

A normalizer is a normalization mechanism for `keyword` fields. Unlike an analyzer, a normalizer has no tokenizer and must output exactly one token. It typically uses character filters and token filters compatible with normalizer constraints, such as lowercase or asciifolding.

For example, suppose an application wants brand codes to be case-insensitive when filtering. You can declare a normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_ascii": {
          "type": "custom",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "brand": {
        "type": "keyword",
        "normalizer": "lowercase_ascii"
      }
    }
  }
}
~~~

When indexing and searching on this field, values are normalized by the same rule. For example, `SONY`, `Sony`, and `sony` are normalized to the same lowercase form. For accented characters, `asciifolding` can convert certain variants to their ASCII equivalents.

Quick comparison:

| Feature | Analyzer | Normalizer |
|---|---|---|
| Primary goal | Analyze text for full-text search | Normalize keyword values |
| Tokenizer | Has exactly one tokenizer | No tokenizer |
| Output token count | Can produce multiple tokens | Always one token |
| Commonly used field | `text` | `keyword` |
| Example | Split a title into words | Normalize brand names for case-insensitive filtering |

Do not use a normalizer in place of an analyzer when word-by-word search is required. Conversely, do not use a tokenized `text` field for whole-value matching, sorting, or aggregations over the entire string. When a property needs both behaviors, create multi-fields.

## 9. Applying analyzers and normalizers in Spring Data Elasticsearch

Spring Data Elasticsearch maps Java entities to Elasticsearch mappings. You can declare analyzers and normalizers in field annotations while providing settings when creating the index.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products")
@Setting(settingPath = "/elasticsearch/product-settings.json")
public class ProductDocument {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "product_index",
        searchAnalyzer = "product_search"
    )
    private String name;

    @Field(
        type = FieldType.Keyword,
        normalizer = "lowercase_ascii"
    )
    private String brand;

    // Constructors, getters, and setters
}
~~~

In the example:

- `@Document` specifies the entity's index.
- `@Setting` points to the settings file containing analyzer and normalizer definitions.
- `@Field(type = FieldType.Text, ...)` maps the product name as a full-text field and selects separate analyzers for indexing and searching.
- `@Field(type = FieldType.Keyword, normalizer = ...)` normalizes the brand while keeping the value as a single token.

Place the configuration file on the classpath, such as `src/main/resources/elasticsearch/product-settings.json`. The file content can include an `analysis` section similar to the custom analyzer and normalizer examples above. Analyzer, search analyzer, and normalizer names in the annotations must match the names declared in settings exactly.

A property may require both full-text search and whole-string matching. You can use multi-fields to index the same value in multiple ways:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@MultiField(
    mainField = @Field(
        type = FieldType.Text,
        analyzer = "product_index",
        searchAnalyzer = "product_search"
    ),
    otherFields = {
        @InnerField(
            suffix = "raw",
            type = FieldType.Keyword,
            normalizer = "lowercase_ascii"
        )
    }
)
private String name;
~~~

The resulting mapping can provide `name` for full-text search and `name.raw` for exact filtering, sorting, or aggregations. Check the actual generated mapping to confirm that all fields and settings were applied.

Annotation attribute names and APIs may differ across Spring Data Elasticsearch versions. When upgrading versions, consult the documentation for the version in use, especially for declaring settings, mappings, and queries.

## 10. Testing analyzers with the Analyze API

Never guess output tokens solely from an analyzer's name. Elasticsearch provides the Analyze API to inspect directly how text is analyzed.

Example invoking an index analyzer:

~~~http
POST /products/_analyze
{
  "analyzer": "product_index",
  "text": "<p>CAFÉ Shoes</p>"
}
~~~

You can ask Elasticsearch to explain each step with the `explain` option:

~~~http
POST /products/_analyze
{
  "analyzer": "product_index",
  "text": "CAFÉ Shoes",
  "explain": true
}
~~~

The response returns the token list and details such as position, offset, and token type; explain mode provides stage-by-stage details. This is useful for verifying that character filters, tokenizer, and token filters behave as intended.

Besides the Analyze API, you can inspect index settings and mappings:

~~~http
GET /products/_settings
GET /products/_mapping
~~~

When testing queries, distinguish between `match` and `term`:

~~~json
{
  "query": {
    "match": {
      "name": "cafe shoes"
    }
  }
}
~~~

`match` analyzes the query string using the field's search analyzer before searching. This is usually the right choice for `text` fields.

~~~json
{
  "query": {
    "term": {
      "brand": "SONY"
    }
  }
}
~~~

`term` searches for an exact indexed value and does not automatically analyze the query string like `match`. For keyword fields with a normalizer, understand how the value is normalized so compatible query values are sent. Do not use `term` on a `text` field for regular full-text search.

## 11. Common configuration mistakes

**Using the wrong field type.** If a field needing full-text search is mapped as `keyword`, `match` queries will not tokenize word-by-word as expected. If a field needing whole-value filtering only exists as `text`, filtering and aggregations may not work properly. Use multi-fields when both are needed.

**Missing analyzer.** The mapping references `product_index`, but settings do not declare that analyzer, or settings were not applied when the index was created. Inspect `_settings` and index creation order.

**Incompatible index and search analyzers.** Tokens produced at search time do not match indexed tokens. Run the Analyze API with both analyzers on representative phrases and compare the outputs.

**Changing annotations without the index changing.** Annotations in Java code describe the mapping Spring Data uses when creating an index. If the index already exists with the old mapping, updating the entity does not mean Elasticsearch automatically modifies the mapping or re-analyzes old data. Typically, you must create a new index with the new settings/mapping, reindex the data, and switch aliases or read traffic to the new index.

**Overly broad n-grams.** N-grams can dramatically increase token counts and index size. Limit min/max gram lengths, use a dedicated field, and benchmark performance with realistic data.

**Excessive accent folding or stemming.** Normalization makes searching more forgiving, but it can erase distinctions between words or codes. Check easily confused word pairs and domain-specific data before applying broadly.

**Assuming default analyzers understand every language.** Word-splitting and stemming rules depend on language. Especially for Vietnamese, splitting on whitespace may not properly recognize compound words. Test with real product queries and content.

## 12. Design and implementation workflow

You can implement in the following order:

1. **Define search behavior.** Clarify whether you need word search, phrase search, case-insensitivity, accent-insensitivity, synonyms, autocomplete, or exact matching.
2. **Choose field types.** Use `text` for content requiring analysis; use `keyword` for codes, statuses, categories, and values needing filtering or grouping; use multi-fields if both are required.
3. **Choose the minimal analyzer.** Start with built-in analyzers. Create custom analyzers only when specific requirements justify them.
4. **Design settings and mapping.** Declare character filters, tokenizer, token filters, normalizers, and bind them to the right fields before creating the index.
5. **Test with the Analyze API.** Check examples with punctuation, uppercase letters, Vietnamese diacritics, compound words, product codes, and synonyms.
6. **Verify real queries.** Compare `match`, phrase query, `term`, filter, and aggregation results against business expectations.
7. **Integrate into Spring Data Elasticsearch.** Declare settings and mappings via annotations or an index-creation mechanism suited to the application architecture; verify the index was created with the intended configuration.
8. **Plan index changes.** When analyzer or mapping changes must be applied to stored data, prepare a reindex and safe cutover plan.

Analyzers determine how text is turned into tokens; tokenizers define token boundaries; token filters transform the token list; normalizers normalize a keyword value into a single token. Understanding each component's role and timing helps design search that is consistent, testable, and aligned with real-world data in Spring Data Elasticsearch applications.
