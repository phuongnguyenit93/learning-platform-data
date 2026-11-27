# Choosing an Analyzer by Language and Content Type

In Elasticsearch, an analyzer determines how text is converted into tokens for indexing and query processing. Choosing the right analyzer helps search match the language accurately and reduces differences caused by capitalization, punctuation, or word variants. Choosing the wrong analyzer can strip away the meaning of content, causing inaccurate results or missing documents even when the keyword appears.

Spring Data Elasticsearch lets you declare analyzers in the mapping using the **@Field** annotation, or manage detailed configuration with JSON settings and mappings via **@Setting** and **@Mapping**. This article presents how to select analyzers by language and data type, with examples for English content, Vietnamese content, product codes, and autocomplete search fields.

## 1. How does an analyzer work?

An analyzer processes text through a sequence of steps. A complete analyzer can consist of:

1. **Character filters**: transform the input string before tokenization, such as stripping HTML tags or replacing specific characters.
2. **Tokenizer**: splits the string into tokens according to rules, such as word boundaries, whitespace, or regular expression patterns.
3. **Token filters**: transform tokens after splitting, such as lowercasing, removing stop words, stemming, folding, or applying synonyms.

For example, the text **"The QUICK foxes!"** passed through an English analyzer may be converted into tokens equivalent to **quick** and **fox** after handling casing, stop words, and stemming. Exact output depends on the analyzer and Elasticsearch version.

Analyzers are used at two stages:

- **Index time**: processes field values before storing tokens in the inverted index.
- **Search time**: processes query text before matching against indexed tokens.

If not declared separately, the search-time analyzer usually inherits the field's analyzer. You can declare **search_analyzer** to process queries with different rules from index time. Both sides must produce compatible tokens; otherwise, queries may fail to match.

### Analysis pipeline illustration

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
List of tokens indexed or used for searching
~~~

Not every field needs an analyzer. Fields containing identifiers, statuses, emails, or values that require exact matching typically use **keyword**. Numeric and date-time fields should use their corresponding data types rather than being stored as text solely for analysis.

## 2. Common analyzers and components

Elasticsearch provides many built-in analyzers and lets you combine components to create custom analyzers.

| Analyzer | General processing behavior | Suitable use cases |
|---|---|---|
| **standard** | Splits on Unicode word boundaries and lowercases | General text, content not yet requiring language-specific handling |
| **simple** | Splits on non-letter characters and lowercases | Simple text consisting only of words |
| **whitespace** | Splits on whitespace | Content that has been preprocessed or word-segmented beforehand |
| **keyword** | Keeps the entire string as a single token | Values requiring exact matching |
| **english**, **french**, **german**, and other language analyzers | Applies language rules such as stop words and stemming | Monolingual content with a known language |
| **pattern** | Splits tokens using a regular expression | Logs, formatted strings, or content with custom delimiters |
| **fingerprint** | Normalizes and sorts tokens into a single representative token | Certain near-duplicate content detection cases |

Built-in analyzers can differ in stop word sets, stemming algorithms, and tokenization rules. Consult the documentation for your exact Elasticsearch version and verify actual output with the **_analyze** API.

### Analyzers and tokenizers are not the same

A tokenizer is only responsible for splitting text into tokens. An analyzer is the complete processing pipeline, consisting of character filters, a tokenizer, and token filters.

For example:

- **standard** is a built-in analyzer that uses the standard tokenizer along with default normalization steps.
- **standard tokenizer** is only a tokenizer, which can be combined with token filters to build a custom analyzer.
- **lowercase** is a token filter that converts tokens to lowercase.
- **asciifolding** is a token filter that converts many accented Unicode characters to their ASCII equivalents.
- **stop** is a token filter that removes words identified as stop words.
- **stemmer** is a token filter that reduces words to an approximate root form according to a language's stemming algorithm.

Do not pick an analyzer just because its name sounds appropriate. Test it on your system's real text, inspect the output token list, and evaluate whether those tokens support your search requirements accurately.

## 3. Choosing an analyzer by language

Language determines word splitting, morphological variants, stop words, and normalization rules. An English analyzer may work well for English text but is unsuitable for Vietnamese or Japanese text.

### English and languages with built-in analyzer support

Elasticsearch provides analyzers for many languages, such as **english**, **french**, **german**, **spanish**, **italian**, **dutch**, **russian**, and several others. Specific analyzers apply language-specific rules such as stop words and stemming.

Example mapping for an English title:

~~~json
{
  "properties": {
    "title_en": {
      "type": "text",
      "analyzer": "english",
      "search_analyzer": "english",
      "fields": {
        "raw": {
          "type": "keyword",
          "ignore_above": 256
        }
      }
    },
    "description_en": {
      "type": "text",
      "analyzer": "english",
      "search_analyzer": "english"
    }
  }
}
~~~

With the **english** analyzer, word variants such as **connect**, **connecting**, or **connected** can be reduced to a root form via stemming. Stop words such as certain articles and prepositions may be removed. This is useful when searching English prose, but may not be suitable for brand names, proper nouns, or technical terms that must remain intact.

If you need an exact title match, use the **title_en.raw** multi-field with a **term** query. The **title_en** field serves full-text search; **title_en.raw** serves exact matching, sorting, or aggregations.

### Vietnamese

Vietnamese has tone marks and multi-syllable words separated by spaces. A phrase may consist of multiple syllables forming a single lexical unit. Therefore, a tokenizer that only splits on whitespace may not accurately recognize Vietnamese word boundaries.

Elasticsearch does not provide a dedicated Vietnamese analyzer in its standard built-in language analyzers. Using **standard** or a custom analyzer with the **standard tokenizer** is a useful starting point for many cases, but it does not perform Vietnamese compound-word segmentation.

For example, the phrase **"học sinh"** may be split into two tokens **học** and **sinh**. That is helpful when users search by individual syllables, but does not fully capture the two syllables combining into one lexical unit. For Vietnamese search systems requiring high accuracy, consider a dedicated Vietnamese word segmenter.

A basic custom analyzer for Vietnamese can lowercase text while preserving diacritics:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "vietnamese_basic": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        }
      }
    }
  }
}
~~~

Preserving diacritics helps distinguish words with different spellings and meanings. If the product requires accent-insensitive search, you can create an additional analyzer using **asciifolding**:

~~~json
{
  "analysis": {
    "analyzer": {
      "vietnamese_folded": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase",
          "asciifolding"
        ]
      }
    }
  }
}
~~~

Do not strip accents by default on every field. Folding collapses many distinct word forms into the same token, which can produce unintended results. A common design is to keep the accented Vietnamese field as the primary field and create an accent-folded multi-field to support supplemental search needs.

When Vietnamese word segmentation is needed, you can use a natural language processing library or service such as VnCoreNLP, Underthesea, or another system-compatible segmenter. Segmentation can be performed at the application layer or in an ingest pipeline, then stored in a separate field. The same segmentation rules must be applied to query text; if you only segment when writing data and not on queries, tokens on both sides may not match.

One design approach is to store both the original content and the segmented content:

- **title_vi**: preserves the original text for display and basic queries.
- **title_vi_segmented**: holds output from the word segmenter, used for Vietnamese word-level search.
- **title_vi_folded**: depending on requirements, holds an unaccented variant to support users typing without diacritics.

Do not treat **asciifolding** as a replacement for word segmentation. Folding handles character forms; segmentation handles word boundaries. These are two distinct concerns.

### Chinese, Japanese, and Korean

For certain East Asian languages, tokenization requires specialized rules. Elasticsearch includes a built-in **cjk** analyzer for handling some CJK text, as well as specialized analysis plugins:

- **analysis-smartcn** provides an analyzer for Simplified Chinese.
- **analysis-kuromoji** provides an analyzer for Japanese.
- **analysis-nori** provides an analyzer for Korean.

Plugins must match the exact Elasticsearch version and be installed on the required nodes according to operational procedures. Some analyzers have their own dictionaries and segmentation rules; output should be tested with real data, especially when proper nouns, domain terminology, or mixed-language text are present.

For Japanese or Korean, using **standard** as a generic analyzer may not meet word segmentation needs. Test specialized analyzers and evaluate result quality before deployment.

## 4. Choosing an analyzer by content type

Besides language, content type also dictates analysis behavior. A product index might contain names, descriptions, SKUs, categories, contact emails, and search suggestion fields. You should not use the same analyzer for all of these fields.

| Content type | Suggested field type or analyzer | Reason |
|---|---|---|
| Natural names and descriptions | **text** with a language-appropriate analyzer | Search by words and word variants |
| SKU codes, order codes, product codes | **keyword** | Preserve exact value for exact matching |
| Categories, statuses, labels | **keyword** | Filtering, grouping, and aggregations |
| Names needing both full-text and exact match | **text** with a **keyword** multi-field | Serve both query types |
| Emails and URLs | **uax_url_email** tokenizer or **keyword** field, depending on requirements | Preserve address and string structure |
| Logs and technical codes | **keyword**, **whitespace**, or **pattern** | Depends on format and delimiters |
| Search-as-you-type suggestions | **search_as_you_type** or custom analyzer with **edge_ngram** | Prefix and partial content matching |
| Monetary amounts, quantities, timestamps | **numeric** or **date** types | Enables proper comparisons, ranges, and sorting |

### Product names and descriptions

Product names often need both full-text search and exact matching. A multi-field can be used:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "english",
    "fields": {
      "raw": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

A **match** query on **name** analyzes keywords using the English analyzer. A **term** query on **name.raw** matches the intact value. If the content is Vietnamese, replace the analyzer with a Vietnamese analyzer suited to the application's segmentation and normalization strategy.

Long descriptions typically use **text** for content-based search. Avoid applying **keyword** to entire long descriptions if users need to search by individual words.

### Identifiers, SKUs, and statuses

SKU codes like **KB-1000-BLK** usually need to remain intact. Use **keyword** to prevent a tokenizer from splitting the code into multiple tokens:

~~~json
{
  "sku": {
    "type": "keyword"
  },
  "status": {
    "type": "keyword"
  }
}
~~~

If codes are case-insensitive, you can use a normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": [
            "lowercase"
          ]
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
~~~

A normalizer transforms a keyword value into a single normalized token. Use it only when business rules specify that codes are case-insensitive. If the system distinguishes **ab-12** and **AB-12**, do not arbitrarily collapse both into the same form.

### Emails and URLs

Email addresses and URLs contain dots, hyphens, `@` symbols, or other delimiters. If you need to search by the full address, using **keyword** is usually easier to control. If you need to tokenize while preserving URL/email structure, consider the **uax_url_email** tokenizer in a custom analyzer.

Do not use a standard language analyzer on URL or email fields if the application requires exact whole-string matching. For querying email domains, hostnames, or URL components, consider storing separate extracted fields such as **emailDomain** or **urlHost**.

### Search-as-you-type suggestions

Autocomplete has different requirements from full-text search. Users may type only the beginning of a word or phrase. Elasticsearch provides the **search_as_you_type** field type, or you can create a custom analyzer with **edge_ngram**.

Example using **search_as_you_type**:

~~~json
{
  "properties": {
    "suggest_name": {
      "type": "search_as_you_type"
    }
  }
}
~~~

This field type creates subfields that support prefix and phrase matching. When finer control is needed, you can use the **edge_ngram** tokenizer or token filter in the index-time analyzer and use a normal analyzer at search time.

Avoid applying **ngram** or **edge_ngram** to every field because token counts can grow rapidly, bloating the index and consuming resources. Create dedicated fields for autocomplete.

## 5. Declaring analyzers in Spring Data Elasticsearch

You can declare analyzers directly with **@Field** if the analyzer already exists in Elasticsearch or is defined in the index settings.

Example document class with English, Vietnamese, and SKU fields:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "products", createIndex = true)
@Setting(settingPath = "/elasticsearch/products-settings.json")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(
        type = FieldType.Text,
        analyzer = "english",
        searchAnalyzer = "english"
    )
    private String titleEn;

    @Field(
        type = FieldType.Text,
        analyzer = "vietnamese_basic",
        searchAnalyzer = "vietnamese_basic"
    )
    private String titleVi;

    @Field(type = FieldType.Text, analyzer = "english")
    private String descriptionEn;

    // Constructors, getters, and setters omitted.
}
~~~

In this example, **vietnamese_basic** is a custom analyzer that must be declared in the settings file. **english** is a built-in Elasticsearch analyzer. Analyzer names in the annotations must match the declared names or built-in analyzer names exactly.

When multi-fields are needed, JSON mapping is often clearer and more flexible. You can declare a mapping with **@Mapping(mappingPath = "...")** on the document class, then keep **@Field** annotations consistent with the JSON structure. Avoid declaring the same field with two conflicting configurations.

An illustrative settings file:

~~~json
{
  "index": {
    "analysis": {
      "analyzer": {
        "vietnamese_basic": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        },
        "vietnamese_folded": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "asciifolding"
          ]
        }
      }
    }
  }
}
~~~

For a multilingual project, the JSON mapping can declare separate fields for each language:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "title_en": {
      "type": "text",
      "analyzer": "english",
      "fields": {
        "raw": {
          "type": "keyword"
        }
      }
    },
    "title_vi": {
      "type": "text",
      "analyzer": "vietnamese_basic",
      "fields": {
        "folded": {
          "type": "text",
          "analyzer": "vietnamese_folded"
        }
      }
    },
    "description_en": {
      "type": "text",
      "analyzer": "english"
    },
    "description_vi": {
      "type": "text",
      "analyzer": "vietnamese_basic"
    },
    "title_vi_segmented": {
      "type": "text",
      "analyzer": "whitespace",
      "search_analyzer": "whitespace"
    }
  }
}
~~~

Field names in JSON must match the actual field names written to Elasticsearch. If the application uses camelCase in Java while the mapping uses snake_case, configure a consistent naming conversion rule or use matching field names in the mapping.

The **title_vi_segmented** field receives text already processed by a word segmenter, with tokens separated by spaces. Therefore, the example uses the **whitespace** analyzer to preserve each token produced by the segmenter. The application must also segment search keywords using the same rules before sending queries.

## 6. Distinguishing `analyzer`, `search_analyzer`, and `normalizer`

These concepts are related but have different scopes of use.

| Property | Used for | Characteristics |
|---|---|---|
| **analyzer** | **text** fields at index time | Converts content into tokens stored in the inverted index |
| **search_analyzer** | **text** fields when analyzing queries | Can differ from the index analyzer but must produce compatible tokens |
| **search_quote_analyzer** | Phrase or quoted queries when configured | Enables separate analysis rules for quoted query strings |
| **normalizer** | **keyword** fields | Normalizes the entire value into a single token without word tokenization |

For example, you can use the English analyzer at both index time and search time:

~~~json
{
  "title": {
    "type": "text",
    "analyzer": "english",
    "search_analyzer": "english"
  }
}
~~~

In some designs, the index analyzer may use stemming or n-grams, while the search analyzer only lowercases. When doing so, inspect output tokens on both sides to ensure queries can still match stored tokens.

A **term query** does not analyze query text the way a **match query** does. When exact matching is needed, use a **keyword** field and a **term** query. When searching natural-language content, use a **text** field and an appropriate **match** or **match_phrase** query.

## 7. Handling multilingual content

A field might contain multiple languages, such as a product description with both Vietnamese and English. If you use an English analyzer for the whole field, Vietnamese words may be processed improperly. If you use a Vietnamese analyzer for the whole field, English content may not be stemmed and filtered properly.

Some common strategies:

**Split fields by language.** Store **description_vi** and **description_en**, and select the query field based on the user's language. This is easy to control when the application knows the language at input time.

**Detect language at ingest time.** The application or data processing service detects the language and writes content to the corresponding field. You need a fallback strategy for short text, proper nouns, or mixed-language snippets because language detection can be inaccurate.

**Store both original and normalized versions.** The original version is used for display; the normalized or segmented version is used for search. This is useful for Vietnamese and other languages needing special preprocessing.

**Use a generic analyzer for mixed-language content.** The **standard** analyzer can be a baseline choice when language cannot be determined, though it will not provide full language-specific stemming or word segmentation.

Do not expect a single analyzer to handle every language optimally. The choice should be based on actual language composition, query types, storage cost, and desired accuracy.

## 8. Testing analyzers with the `_analyze` API

Before creating an index in a live environment, test your analyzers with strings representative of your application's data.

Test a built-in analyzer:

~~~http
POST /_analyze
{
  "analyzer": "english",
  "text": "The running shoes are comfortable"
}
~~~

Test a Vietnamese custom analyzer:

~~~http
POST /_analyze
{
  "analyzer": "vietnamese_basic",
  "text": "Trường đại học ở Thành phố Hồ Chí Minh"
}
~~~

Test an accent-folded analyzer:

~~~http
POST /_analyze
{
  "analyzer": "vietnamese_folded",
  "text": "Thành phố Hồ Chí Minh"
}
~~~

You can test the analyzer bound to a field after the index has been created:

~~~http
POST /products/_analyze
{
  "field": "title_vi",
  "text": "Trường đại học Bách khoa"
}
~~~

When reviewing the output, pay attention to:

- The number of tokens generated.
- Whether tokens retain diacritics.
- Whether capitalization is normalized.
- Whether stop words are unintentionally removed.
- Whether compound words or important terms are split incorrectly.
- Whether input text produces tokens matching how queries are expected to be analyzed.

Create a test dataset containing proper nouns, accented words, unaccented words, numbers, product codes, punctuation, abbreviations, and mixed-language text. Do not test with only one simple sentence, as many analyzer issues only surface with real-world data.

## 9. Verifying search results after selecting an analyzer

The **_analyze** API shows how text is converted into tokens, but it does not prove that search results meet business requirements. After creating the index, index some sample documents and run representative queries.

Example full-text search:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "title_en": "running shoe"
    }
  }
}
~~~

Example exact SKU match:

~~~http
GET /products/_search
{
  "query": {
    "term": {
      "sku": "KB-1000-BLK"
    }
  }
}
~~~

Example Vietnamese search on a segmented field:

~~~http
GET /products/_search
{
  "query": {
    "match": {
      "title_vi_segmented": "học sinh"
    }
  }
}
~~~

If results are not as expected, check both the mapping and the tokens. A **term** query on a **text** field may not behave as expected because the field has been analyzed. Conversely, a **match** query on a **keyword** field does not provide full-text search behavior like a **text** field.

You can use **_termvectors** to inspect terms stored for a specific document, or **_explain** to understand why a document matched or failed to match a query. These APIs are useful for deeper diagnosis after checking the analyzer.

## 10. Common mistakes when choosing an analyzer

| Symptom | Possible cause | Resolution |
|---|---|---|
| Vietnamese search misses results | Only using whitespace-based tokenization without handling compound words | Assess word segmentation needs; consider a Vietnamese segmenter |
| Users enter unaccented text and get no matches | Index preserves diacritics while query has none | Create a separate folded field or normalize both sides with the same rules |
| SKU search returns unexpected results | Using a text analyzer splits the code into multiple tokens | Change the code field to `keyword` |
| English search drops important words | Stop words or stemming unsuitable for proper nouns and technical terms | Use a different analyzer or a separate field for content that must remain intact |
| Multilingual search lacks accuracy | Using a single language analyzer for mixed-language text | Split fields, detect language, or intentionally use a generic analyzer |
| Query does not match even though the word appears in the document | Index analyzer and search analyzer produce different tokens | Compare `_analyze` output on both sides |
| Index size grows rapidly | Unnecessary n-grams or excessive multi-fields | Only create fields that serve actual search requirements |
| Custom analyzer fails index creation | Missing analyzer, tokenizer, plugin, or invalid settings configuration | Check settings, Elasticsearch logs, and plugins across nodes |

One critical mistake is changing an analyzer in a configuration file and expecting the existing index to update automatically. Analyzers are bound to index mappings and settings; changes may require creating a new index and reindexing data. Define the index lifecycle before deploying changes.

## 11. Workflow for choosing an analyzer in a project

You can apply the following workflow when designing mappings:

1. **Identify languages.** Note the languages in your data, likelihood of mixed languages, and how language is detected.
2. **Classify fields.** Identify whether a field is natural text, an identifier, category, email, URL, number, date, or suggestion content.
3. **Determine query types.** Distinguish full-text search, exact matching, phrase queries, filtering, sorting, aggregations, and autocomplete.
4. **Pick an initial analyzer.** Use an appropriate built-in analyzer if available; create a custom analyzer when custom rules are needed.
5. **Design multi-fields when needed.** A field can have a `text` version for search and a `keyword` version for exact matching.
6. **Inspect tokens.** Use the **_analyze** API with a dataset close to real data.
7. **Test queries.** Create sample documents and run the queries the application will execute.
8. **Evaluate cost.** Consider index size, write speed, search latency, and accuracy.
9. **Package configuration.** Place settings and mappings in resources, binding them to the document class with **@Setting** and **@Mapping** if the application manages indices this way.
10. **Plan changes.** When mappings or analyzers change incompatibly, create a new index and reindex rather than assuming existing configurations update automatically.

A good analyzer fits the language, content type, and how users search in the application. For English, built-in language analyzers can provide useful stemming and stop words. For Vietnamese, pay attention to the difference between syllable splitting and word segmentation; accent folding only addresses character normalization. For identifiers and values needing exact matching, **keyword** is usually more suitable than a text analyzer. Testing tokens and queries on representative data is an essential step before putting a mapping into production.
