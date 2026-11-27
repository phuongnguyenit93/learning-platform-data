# Building an Analyzer from Character Filters, Tokenizer, and Token Filters

Elasticsearch searches text based on tokens generated at index time and during query processing. An **analyzer** is the component that determines how a text string is normalized and split into tokens. In Spring Data Elasticsearch, analyzers are declared in field mappings and executed by Elasticsearch when the application writes or searches documents.

A custom analyzer typically consists of three groups of components in exact processing order:

1. **Character filters**: modify the input character string before tokenization, such as stripping HTML or replacing characters.
2. **Tokenizer**: splits the processed string into tokens based on boundary rules, such as word boundaries or whitespace.
3. **Token filters**: transform, remove, or expand tokens, such as lowercasing, removing stop words, stemming, or applying synonyms.

Choosing and ordering these components determines which words can match a query. A well-designed analyzer aligns search results with user language while preserving exact filtering capabilities on identifier fields.

## 1. How does an analyzer process text?

When Elasticsearch indexes a `text` field, the field's analyzer converts the value into a stream of tokens. When running a query such as `match`, the search analyzer processes user-entered text to produce query tokens. If both sides normalize compatibly, the tokens can match.

Pipeline diagram:

~~~mermaid
flowchart TD
    A["Input string"] --> B["Character filters"]
    B --> C["Tokenizer"]
    C --> D["Token filters"]
    D --> E["Token list"]
    E --> F["Elasticsearch indexes or generates query terms"]
~~~

For example, the input text may contain HTML, uppercase letters, Vietnamese diacritics, or special characters:

~~~text
<b>Cà Phê</b> & Accessories
~~~

An analyzer can:

- Strip HTML tags such as `<b>`.
- Normalize diacritics or characters according to the search policy.
- Split text into words.
- Convert tokens to lowercase.
- Remove words with little search value (stop words) if appropriate.

The result is a sequence of tokens used by Elasticsearch for indexing. `_source` still retains the original JSON content of the document; the analyzer does not overwrite the original string in `_source`.

## 2. Character filter — processing characters before tokenization

A character filter receives the entire input string and returns a transformed string to the tokenizer. Multiple character filters can be combined; they execute in the declared order.

Common character filters:

| Character filter | Purpose |
| --- | --- |
| `html_strip` | Removes HTML tags and decodes HTML entities. Useful when descriptions contain markup. |
| `mapping` | Replaces specific strings or characters according to mapping pairs. |
| `pattern_replace` | Replaces substrings matching a regular expression with another string. |

### 2.1. `html_strip`

`html_strip` strips HTML tags before the tokenizer processes the text. Example input:

~~~html
<p>Wireless <strong>Keyboard</strong></p>
~~~

After stripping tags, the tokenizer receives the text `Wireless Keyboard`. HTML entities such as `&amp;` are also handled according to HTML rules.

This is useful when content comes from a CMS, product descriptions, or formatted HTML articles. If the input is already plain text, there is no need to add this filter.

### 2.2. `mapping`

`mapping` replaces declared characters or strings before the tokenizer runs. For example, you can normalize `&` into the word `and` so both spellings produce compatible tokens:

~~~json
{
  "type": "mapping",
  "mappings": [
    "& => and",
    "+ => plus"
  ]
}
~~~

Mappings are applied according to the list. Choose rules carefully because replacements can alter data meaning or create new tokens. If a mapping replaces one character with multiple characters, the tokenizer sees the post-replacement string.

### 2.3. `pattern_replace`

`pattern_replace` uses a regular expression to replace a character pattern. For example, normalizing multiple consecutive hyphens or underscores into a single space:

~~~json
{
  "type": "pattern_replace",
  "pattern": "[-_]+",
  "replacement": " "
}
~~~

With the input `wireless__keyboard-pro`, the string after the character filter becomes `wireless keyboard pro`. This rule is helpful when data comes from multiple sources with inconsistent delimiter conventions.

Regular expressions should be tested against real data. Overly broad patterns can delete meaningful characters, and complex patterns can increase processing overhead.

## 3. Tokenizer — splitting text into tokens

The tokenizer receives the string after character filters and determines token boundaries. Each analyzer has one tokenizer. Choosing a tokenizer depends on the data type and how users search.

| Tokenizer | Splitting behavior | Common use cases |
| --- | --- | --- |
| `standard` | Splits according to Unicode word segmentation rules and handles common punctuation. | Natural text, descriptions, titles. |
| `whitespace` | Splits on whitespace; punctuation can remain inside tokens. | Data already normalized by whitespace. |
| `keyword` | Keeps the entire string as a single token. | When treating the full value as one unit; typically used with keyword fields or normalizers. |
| `letter` | Splits on non-letter characters. | Text where word boundaries are primarily defined by letters. |
| `pattern` | Splits according to a regular expression. | Data with specialized delimiter formats. |
| `ngram` | Generates substrings of lengths within a configured range. | Approximate matching or substring-based autocomplete. |
| `edge_ngram` | Generates prefixes of tokens. | Prefix-based autocomplete from the start of words. |

### 3.1. `standard`

`standard` is a suitable choice for many kinds of natural text. It detects word boundaries based on Unicode rules and handles various types of punctuation.

For example, with `Wireless Keyboard, Model X100`, the standard tokenizer creates tokens at word boundaries; downstream token filters then continue normalizing them.

### 3.2. `keyword`

The `keyword` tokenizer keeps the entire input as a single token. If the string is `SKU-AB_123`, the tokenizer does not split it into `SKU`, `AB`, and `123`.

This differs from the `keyword` mapping field type in Elasticsearch:

- The `keyword` tokenizer is an analyzer component.
- The `keyword` field type is a mapping type commonly used for values needing exact matching.

A `keyword` field can use a normalizer to lowercase or strip accents while keeping a single token. You do not need to create a custom analyzer with the `keyword` tokenizer solely to index identifiers; choose the field type that fits the query purpose.

### 3.3. `ngram` and `edge_ngram`

`ngram` generates multiple consecutive substrings anywhere within each token. `edge_ngram` only generates substrings anchored at the start of the token.

For example, the token `phone` with `edge_ngram` using `min_gram: 2` and `max_gram: 5` can generate prefixes such as `ph`, `pho`, `phon`, `phone`. A user typing `pho` can find documents containing `phone`.

These tokenizers increase token count and index size. Use them for specific autocomplete use cases, typically combining a dedicated index-time analyzer with a simpler search-time analyzer. Do not apply n-grams to every text field.

## 4. Token filter — transforming tokens after splitting

The tokenizer creates initial tokens. Token filters further normalize, remove, or expand those tokens. Multiple filters can be used; the order of declaration directly affects the output.

Common token filters:

| Token filter | Effect |
| --- | --- |
| `lowercase` | Converts tokens to lowercase. |
| `uppercase` | Converts tokens to uppercase. |
| `asciifolding` | Converts many accented characters into ASCII equivalents, e.g., `café` to `cafe`. |
| `stop` | Removes stop words according to a configured list. |
| `stemmer` | Reduces words to an approximate root form by language, such as plural or verb tense variants. |
| `synonym_graph` | Expands or replaces synonyms, supporting multi-token phrases in search queries. |
| `word_delimiter_graph` | Splits or combines parts of compound words, codes, and delimited strings. |
| `ngram` / `edge_ngram` | Creates sub-tokens or prefixes from existing tokens. |

### 4.1. `lowercase`

`lowercase` normalizes letter case so queries do not depend on capitalization. For example, `Wireless`, `WIRELESS`, and `wireless` are all normalized to `wireless`.

This filter commonly appears in analyzers for natural text. If original capitalization must be preserved for display, `_source` retains the original value; normalized tokens only serve search.

### 4.2. `asciifolding`

`asciifolding` converts many accented characters to close ASCII equivalents. For example, `café` becomes `cafe`, and `résumé` becomes `resume`.

This enables users to find accented content with unaccented queries in some languages. However, stripping accents can erase distinctions between words; you should decide based on language and business requirements. For Vietnamese, test on real data to evaluate how tone marks and special letters are normalized before applying it broadly.

### 4.3. `stop`

The stop filter removes words that occur very frequently and contribute little to distinguishing results. You can use a built-in stop word set such as `_english_`, or provide a custom list.

Example configuration:

~~~json
{
  "type": "stop",
  "stopwords": ["the", "a", "an", "and", "or"]
}
~~~

Do not use the English stop word list by default for Vietnamese content. Removing stop words can affect query meaning, especially in short phrases or negated expressions. Select the list according to the language of the data.

### 4.4. `stemmer`

Stemming reduces word variants to an approximate root form so queries can match multiple grammatical forms. For example, in English, `connect`, `connected`, and `connecting` can be reduced to a corresponding root form depending on the stemmer algorithm.

Elasticsearch provides language-specific stemmers. For example, a `stemmer` filter can set `language: "english"`. Do not use an English stemmer for Vietnamese; if Vietnamese morphological handling is needed, choose a tool or analyzer suitable for that language.

### 4.5. `synonym_graph`

`synonym_graph` supports synonyms, including multi-token phrases. For example, you can declare `tv` and `television` as equivalents so users searching with one spelling still receive documents containing the other.

For phrase search, `synonym_graph` is typically used in the search analyzer to generate an accurate token graph. Carefully verify synonym rules, token filter ordering, and phrase query behavior using `_analyze` along with real queries.

## 5. Combining components into a custom analyzer

A custom analyzer is declared under `settings.analysis.analyzer`. Each analyzer specifies character filters, a tokenizer, and a list of token filters.

Example creating an analyzer for product names that may contain HTML, accented Latin characters, and common delimiters:

~~~json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "html_cleaner": {
          "type": "html_strip"
        },
        "symbol_mapping": {
          "type": "mapping",
          "mappings": [
            "& => and",
            "+ => plus"
          ]
        }
      },
      "filter": {
        "english_stop": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "catalog_text": {
          "type": "custom",
          "char_filter": [
            "html_cleaner",
            "symbol_mapping"
          ],
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding",
            "english_stop",
            "english_stemmer"
          ]
        }
      },
      "normalizer": {
        "catalog_keyword": {
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
      "name": {
        "type": "text",
        "analyzer": "catalog_text",
        "search_analyzer": "catalog_text",
        "fields": {
          "raw": {
            "type": "keyword",
            "normalizer": "catalog_keyword"
          }
        }
      },
      "sku": {
        "type": "keyword"
      }
    }
  }
}
~~~

In this configuration:

- `html_cleaner` removes HTML before the tokenizer runs.
- `symbol_mapping` normalizes `&` and `+` to corresponding words.
- `standard` splits the string into tokens.
- `lowercase` and `asciifolding` normalize letter case and diacritics.
- `english_stop` removes English stop words.
- `english_stemmer` handles English word variants.
- `catalog_keyword` is a normalizer for the `name.raw` subfield; it keeps the value as a single token while lowercasing and folding accents.

For example, the product name `Café <b>Accessories</b> & Tools` has HTML stripped, `&` normalized, is split into tokens, and is converted to normalized forms. The final tokens depend on each filter and configured stop word set.

The `name` field uses the `catalog_text` analyzer for full-text search. The `name.raw` subfield uses type `keyword` for exact matching, sorting, or aggregations on the normalized value. The two fields serve two different query types.

## 6. Testing an analyzer with the `_analyze` API

You should not just look at a configuration and assume the analyzer produces the desired tokens. Elasticsearch provides the `_analyze` API to observe actual output.

Once the index is created, send a request:

~~~http
POST /catalog/_analyze
Content-Type: application/json

{
  "analyzer": "catalog_text",
  "text": "Café <b>Accessories</b> & Tools",
  "explain": true
}
~~~

The result contains a list of tokens and attributes such as `token`, `start_offset`, `end_offset`, `type`, and `position`. With `explain: true`, Elasticsearch can provide additional details about each processing stage so you can inspect the impact of character filters, tokenizer, and token filters.

You can test a tokenizer or token filter individually by passing its configuration directly to `_analyze`, or call an analyzer declared in the index. When debugging, change one component at a time to identify which filter drops or transforms a token unexpectedly.

Testing the analyzer of a specific field can also be done using `field` instead of `analyzer` in the `_analyze` request. This verifies the analyzer attached to the field by the mapping.

## 7. Attaching an analyzer to a field mapping

Defining an analyzer in index settings is not enough. The field must reference the analyzer in the mapping:

~~~json
{
  "properties": {
    "description": {
      "type": "text",
      "analyzer": "catalog_text",
      "search_analyzer": "catalog_text"
    },
    "sku": {
      "type": "keyword"
    }
  }
}
~~~

`analyzer` is the analyzer used when indexing field values. `search_analyzer` is the analyzer used to process query text. If `search_analyzer` is omitted, Elasticsearch typically uses the field's analyzer for searching by default.

Different analyzers can be used for index and search. For example, autocomplete might use `edge_ngram` at index time while using `standard` when analyzing queries. This prevents user queries from also being expanded into unnecessary prefixes.

A custom analyzer must exist in the index settings before the mapping references it. An analyzer is not a setting that can be arbitrarily attached to a field after data has already been indexed.

## 8. Using analyzers in Spring Data Elasticsearch

Spring Data Elasticsearch lets you declare mappings with annotations. `@Field` provides `analyzer` and `searchAnalyzer` attributes to reference analyzer names defined in index settings.

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog")
public class Product {

    @Id
    private String id;

    @Field(
        type = FieldType.Text,
        analyzer = "catalog_text",
        searchAnalyzer = "catalog_text"
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String sku;

    // Constructor, getters, and setters
}
~~~

These annotations describe the field mapping. The definition of `catalog_text` must be provided in the index settings. You can manage settings using a JSON file on the classpath and the `@Setting` annotation on the entity:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "catalog")
@Setting(settingPath = "/elasticsearch/catalog-settings.json")
public class Product {
    // Fields and mapping annotations
}
~~~

Place the settings file at `src/main/resources/elasticsearch/catalog-settings.json` in the settings format supported by your project's Spring Data Elasticsearch version. `@Setting` enables Spring Data to apply the index configuration when creating the index from entity metadata.

If the index is created and managed separately via migrations or REST APIs, ensure settings are applied before Spring Data writes documents. The `@Field` annotation does not automatically modify the analyzer of an existing index.

## 9. Index analyzer and search analyzer

The index-time analyzer and search-time analyzer need to be compatible in how they normalize tokens. If indexing converts all tokens to lowercase while searching preserves uppercase, queries may fail to match as expected.

Two separate analyzers can be declared:

- **Index analyzer:** optimizes tokens stored in the inverted index. May use stemming or edge n-grams depending on requirements.
- **Search analyzer:** normalizes queries in a way compatible with indexed tokens; usually avoids generating excessive extra tokens.

For example, in autocomplete, the index analyzer uses `edge_ngram` to create prefixes, while the search analyzer only uses `standard` and `lowercase`. When a user types `key`, the query produces the token `key`, which can match the indexed prefix of `keyboard`.

Do not add stemming, synonyms, or stop filters arbitrarily to both sides. Inspect tokens across both pipelines and confirm that real queries still produce accurate results.

## 10. Synonyms and token filter ordering

When synonym support is required, you can create a `synonym_graph` filter and attach it to the search analyzer. Example configuration under `analysis.filter`:

~~~json
{
  "catalog_synonyms": {
    "type": "synonym_graph",
    "synonyms": [
      "tv, television",
      "laptop, notebook"
    ]
  }
}
~~~

The search analyzer can reference this filter after casing normalization steps:

~~~json
{
  "type": "custom",
  "char_filter": ["html_cleaner"],
  "tokenizer": "standard",
  "filter": [
    "lowercase",
    "asciifolding",
    "catalog_synonyms"
  ]
}
~~~

The position of the synonym filter matters because preceding filters affect how synonyms are analyzed. If using a stop filter or stemmer, check how synonym rules are processed. For multi-word synonyms, `synonym_graph` is more suitable than the simple `synonym` filter to preserve token position relationships for phrase queries.

Managing synonyms in static configuration requires creating or updating index settings through an appropriate workflow. If using a synonym file or the reload search analyzers API, follow the constraints and reload mechanisms of the deployed Elasticsearch version.

## 11. Considerations for the Vietnamese language

The `english_stop` and `english_stemmer` examples are only suitable for English text. They should not be used as-is for fields containing Vietnamese.

For Vietnamese, clearly define search requirements:

- Do users need to search without diacritics and still match accented text?
- Is handling of compound words or syllable boundaries required?
- Should stop words be removed, and which stop word list accurately reflects the domain?
- Is a dedicated Vietnamese word segmenter needed?

The `standard` tokenizer detects boundaries according to Unicode rules but is not a semantic Vietnamese word segmenter. `asciifolding` also does not guarantee all Vietnamese spelling differences are normalized according to product needs. Test the analyzer on a representative set of sentences, including accented words, unaccented words, proper nouns, product codes, and compound words.

When specialized word segmentation is needed, consider an analysis plugin compatible with your Elasticsearch version or preprocess text before indexing. Plugins must be installed on every relevant node in the cluster and match the server version exactly.

## 12. Changing an analyzer after an index already exists

Analyzers and tokenizers used during indexing affect the inverted index. If you want to change how a field with existing data is analyzed, merely editing annotations or settings in application files does not regenerate old tokens.

Typically you need to create a new index with the desired settings/mapping, then reindex documents from the old index to the new index. Read/write aliases can be switched to the new index after verifying the data and mapping.

Some search analyzers can be reloaded if configured with filters that support reloadable synonyms and Elasticsearch supports that operation. Reloading does not apply to every tokenizer, character filter, or analyzer; changing the index analyzer usually requires reindexing to rebuild tokens.

Safe change procedure:

1. Record the current analyzer and mapping.
2. Create a new index with the new settings and mapping.
3. Run `_analyze` with a representative dataset to confirm tokens.
4. Reindex documents to the new index.
5. Run real queries to compare results.
6. Switch aliases or application configuration to the new index.
7. Delete the old index only after confirming no consumers need it and a recovery plan is in place.

## 13. Common mistakes when creating custom analyzers

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Index creation reports missing analyzer or filter | Component name in analyzer does not match declaration, or settings were not sent during index creation. | Check `analysis.char_filter`, `analysis.filter`, `analysis.tokenizer`, and `analysis.analyzer`. |
| Field cannot find analyzer | Mapping references a wrong analyzer name, or analyzer is not defined in index settings. | Define the analyzer first, then create the mapping. |
| Query does not match even though text looks similar | Index analyzer and search analyzer produce different tokens, or a filter removed a token. | Use `_analyze` to inspect both pipelines. |
| Vietnamese words processed improperly | Using English stop words/stemmer or assuming standard tokenizer performs Vietnamese word segmentation. | Build a language-appropriate analyzer and test on real data. |
| Mapping update does not change old results | Tokens in the inverted index have not been regenerated. | Create a new index and reindex data. |
| `dynamic: strict` rejects documents with new fields | Analyzer/type hint or another field was sent that is missing from the mapping. | Declare required fields or intentionally adjust the dynamic policy. |

## 14. Analyzer design workflow

When creating an analyzer for a field, follow this sequence:

1. Collect real data samples, including punctuation, HTML, mixed casing, diacritics, and potential formatting quirks.
2. Determine desired normalization behavior before tokenization; choose appropriate character filters.
3. Choose a tokenizer suited to the data structure and search type.
4. Choose token filters based on language and search goals; arrange them in the proper order.
5. Create the custom analyzer in index settings and attach it to the field mapping.
6. Use `_analyze` to observe tokens and explain each step.
7. Test both the index-time analyzer and search-time analyzer.
8. Run real queries, evaluating accuracy and index size growth overhead.
9. When analyzer changes affect stored tokens, create a new index and reindex.

A custom analyzer is an ordered pipeline: character filters modify the string, a tokenizer determines token boundaries, and token filters normalize or transform tokens. In Spring Data Elasticsearch, `@Field` references the field's analyzer while `@Setting` can provide index settings during index creation. Inspecting tokens with `_analyze` before applying an analyzer to important data helps catch discrepancies between indexing and user search behavior early.
