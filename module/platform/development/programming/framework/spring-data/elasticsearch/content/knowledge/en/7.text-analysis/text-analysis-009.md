# Vietnamese Search, Vietnamese Diacritics, and Plugin Requirements

Vietnamese search in Elasticsearch must simultaneously handle Unicode representations, tone marks, the letter `đ`, word segmentation, and the matching strictness desired by the product. A configuration that only lowercases text is insufficient for accent-insensitive search. Conversely, stripping all diacritics across every field can erase semantic distinctions between Vietnamese words.

In Spring Data Elasticsearch, the application defines analyzers in index settings and maps document fields to those analyzers. Elasticsearch executes tokenization and text analysis on the server side. Built-in filters such as `lowercase` and `asciifolding` require no plugins; if ICU components are needed, the exact matching version of the `analysis-icu` plugin must be installed on Elasticsearch nodes. The ICU plugin handles Unicode better in many cases, but it is not itself a dictionary-based Vietnamese word segmenter.

## 1. Characteristics to handle in Vietnamese search

### Tone marks and diacritics

Vietnamese uses tone marks and diacritical marks to distinguish pronunciation as well as meaning. For example:

| Accented | Unaccented |
|---|---|
| tiếng Việt | tieng Viet |
| Đà Nẵng | Da Nang |
| trường học | truong hoc |
| cửa hàng | cua hang |
| thủ đô | thu do |

Users may type with or without diacritics depending on their device, keyboard, and habits. If the system only indexes accented text and searches with unaccented strings, queries may fail to match. One option is to add an accent-folded field to support flexible search.

### The letters `đ` and `Đ`

The letter `đ`/`Đ` is a distinct letter in Vietnamese. It is not simply a letter `d` with a standard Unicode combining diacritic. Therefore, do not assume every accent-stripping filter converts `đ` to `d` as desired.

When building an accent-insensitive analyzer, test pairs like `điện`/`dien`, `Đà Nẵng`/`Da Nang`, and `Đặng`/`Dang` explicitly. If the chosen filter does not handle this letter as expected, add explicit mappings `đ => d` and `Đ => D` before the lowercase step.

### Precomposed and decomposed Unicode

An accented Vietnamese character can be represented by a precomposed code point or by a base letter plus combining marks. Two visually identical strings can have different code point sequences. This is the difference between Unicode NFC and NFD.

For example, the character `ế` can be represented as a single precomposed character or as `e` plus multiple combining diacritics. When comparing strings at the application layer or passing data across systems, normalize Unicode consistently, typically to NFC. NFC normalization does not remove diacritics; it only normalizes equivalent representations of the same text.

Java example:

```java
import java.text.Normalizer;

public final class VietnameseTextNormalizer {

    private VietnameseTextNormalizer() {}

    public static String toNfc(String value) {
        if (value == null) {
            return null;
        }
        return Normalizer.normalize(value, Normalizer.Form.NFC);
    }
}
```

Unicode normalization and accent stripping are two different operations. Do not use an accent-stripping function as a replacement for NFC when the goal is preserving spelling.

### Vietnamese word segmentation

Vietnamese typically writes syllables separated by spaces. A phrase may consist of multiple syllables acting as a single lexical unit, such as `học sinh`, `nhà đất`, `công nghệ thông tin`. A general word-boundary tokenizer may emit tokens for each syllable rather than recognizing the whole compound phrase via a dictionary.

This does not mean a standard tokenizer is always wrong. For many search features, space-delimited syllable tokens are still useful. However, if the product needs compound-word matching, synonyms, stemming, or dictionary-based Vietnamese word segmentation, an appropriate language processing step must be added.

`analysis-icu` provides general-purpose Unicode tokenizers and filters. It does not automatically become a dictionary-based Vietnamese word segmenter and does not emit compound tokens like `học_sinh` or `công_nghệ_thông_tin`. Word segmentation can be performed before indexing using a Vietnamese NLP library/service, or via a third-party Vietnamese analysis plugin thoroughly evaluated for compatibility and maintenance.

## 2. Accent-sensitive vs. accent-insensitive search

Before configuring analyzers, decide which kind of search the product needs.

### Accent-sensitive search

Accent-sensitive search preserves spelling distinctions. For example, querying `ma` does not automatically match `má`, `mà`, `mả`, `mã`, or `mạ`. This suits proper nouns, content requiring exact matches, and fields where diacritics change meaning.

### Accent-insensitive search

Accent-insensitive search allows the query `tieng viet` to match `tiếng Việt`, or `da nang` to match `Đà Nẵng` if the analyzer handles both diacritics and `đ` according to the chosen rules.

This improves findability when users omit diacritics, but collapses distinct words into the same form after folding. For instance, `ma`, `má`, `mà`, `mả`, `mã`, and `mạ` can all normalize to `ma`. Therefore, do not strip diacritics from original data or rely solely on a folded field for every purpose.

### Combining both with multi-fields

A useful design keeps the accent-sensitive main field and adds a folded subfield. At query time, you can prioritize the accented field and use the unaccented field as a fallback/expansion.

Example:

| Field | Analyzer | Role |
|---|---|---|
| `title` | `vi_sensitive` | Preserves diacritics to prioritize exact spelling matches |
| `title.folded` | `vi_folded` | Supports users typing without diacritics |

Queries can boost `title` higher and give `title.folded` a lower boost. This preserves accent-sensitive ranking while still supporting lenient search.

## 3. Built-in text analysis components

Elasticsearch provides several built-in analyzers and token filters that require no extra plugins:

- `standard` tokenizer: splits text using standard Unicode token boundary rules.
- `lowercase` token filter: converts tokens to lowercase.
- `asciifolding` token filter: converts many accented characters to ASCII equivalents.
- `stop` token filter: removes stop words according to a configured list.
- `synonym` or `synonym_graph`: handles synonyms per configuration.

To build a basic accent-stripping analyzer, you can combine `standard`, `lowercase`, and `asciifolding`. This configuration does not require `analysis-icu`.

Still, verify actual output on Vietnamese data, especially `đ`, decomposed Unicode forms, punctuation, and proper nouns. Do not assume every Vietnamese character converts to the expected ASCII form just because `asciifolding` is enabled.

## 4. Building a basic Vietnamese analyzer without plugins

The following index settings example defines one accent-preserving analyzer and one basic accent-stripping analyzer. Explicit character mappings for `đ`/`Đ` are included so behavior does not depend on whether folding handles that letter.

```json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "vi_d_mapping": {
          "type": "mapping",
          "mappings": [
            "đ => d",
            "Đ => D"
          ]
        }
      },
      "analyzer": {
        "vi_sensitive": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase"
          ]
        },
        "vi_folded": {
          "type": "custom",
          "char_filter": [
            "vi_d_mapping"
          ],
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
```

`vi_sensitive` lowercases while keeping diacritics. `vi_folded` replaces `đ`/`Đ` first, then tokenizes, lowercases, and folds accented characters. This is a basic analyzer for token-level word search; it does not solve dictionary-based Vietnamese word segmentation.

### Creating the index and testing the analyzer

You can create the index via the REST API:

```http
PUT /articles
Content-Type: application/json

{
  "settings": {
    "analysis": {
      "char_filter": {
        "vi_d_mapping": {
          "type": "mapping",
          "mappings": ["đ => d", "Đ => D"]
        }
      },
      "analyzer": {
        "vi_sensitive": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase"]
        },
        "vi_folded": {
          "type": "custom",
          "char_filter": ["vi_d_mapping"],
          "tokenizer": "standard",
          "filter": ["lowercase", "asciifolding"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "vi_sensitive",
        "fields": {
          "folded": {
            "type": "text",
            "analyzer": "vi_folded"
          }
        }
      }
    }
  }
}
```

Test the accent-folded analyzer:

```http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "vi_folded",
  "text": [
    "Tiếng Việt có dấu",
    "Đà Nẵng",
    "Đặng Thị Hòa",
    "hoà bình"
  ]
}
```

Test the accent-sensitive analyzer:

```http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "vi_sensitive",
  "text": [
    "Tiếng Việt có dấu",
    "Đà Nẵng",
    "Đặng Thị Hòa"
  ]
}
```

The `_analyze` endpoint returns actual tokens. Use its output to verify that `đ`, Vietnamese diacritics, and token boundaries behave as required before putting the analyzer into production mappings.

## 5. When is the `analysis-icu` plugin needed?

ICU is the International Components for Unicode library suite. The `analysis-icu` plugin adds ICU-based analysis components to Elasticsearch, such as:

- `icu_tokenizer`: a tokenizer based on ICU's Unicode word boundary rules.
- `icu_folding`: a token filter performing Unicode case folding and folding many diacritics/character equivalents.
- `icu_normalizer`: normalizes Unicode tokens according to a configured normalization form.
- Other ICU components for collation or Unicode transforms.

This plugin is useful when you need more consistent multilingual Unicode handling or ICU tokenizer/normalizer rules. It is not mandatory for every Vietnamese application. If the `standard` tokenizer with `asciifolding` meets your requirements and output has been verified, an additional plugin may be unnecessary.

### ICU does not equal a Vietnamese word segmenter

`icu_tokenizer` applies general Unicode word boundary rules. It can improve handling of Unicode, punctuation, and certain scripts, but it does not automatically use a Vietnamese dictionary to recognize multi-syllable compound words.

If product requirements demand recognizing `học sinh` as one lexical unit, Vietnamese synonym matching, stemming, or morphological handling, a specialized segmentation/language step is needed. You can:

1. Preprocess text with a Vietnamese segmentation library in the application or an NLP service.
2. Write an extra segmented field into the document while keeping the original field for display.
3. Use a third-party Elasticsearch plugin if the project has evaluated its provenance, version support, maintainability, and security.

Do not install a plugin merely because its name contains `Vietnamese`. Verify that the plugin supports your exact Elasticsearch version, how its tokenizer works, how its dictionary is updated, and how it handles real Vietnamese data.

## 6. Installing the `analysis-icu` plugin

`analysis-icu` is a server-side Elasticsearch plugin. Adding a Maven/Gradle dependency to a Spring Boot application does not install the plugin on the cluster. The plugin must be installed on Elasticsearch nodes that handle indexing/querying, and Elasticsearch must be restarted to load it.

### Installing on an Elasticsearch host

Run the command using the Elasticsearch administration account and environment on each node:

```bash
bin/elasticsearch-plugin install analysis-icu
```

The plugin must match the running Elasticsearch version. The plugin installer bundled with the Elasticsearch distribution fetches the matching plugin release. After installation, restart nodes following your cluster's operational procedure.

Verify the plugin is loaded:

```http
GET /_nodes/plugins
```

In the response, confirm nodes list the `analysis-icu` plugin. All nodes that may receive index creation requests or execute analysis need the appropriate plugin. In production clusters, plan synchronized deployment and rolling restarts according to Elasticsearch operational guidelines.

### Installing in a Docker image

With Docker, build a custom image with the plugin installed at image build time. Example:

```dockerfile
FROM docker.elastic.co/elasticsearch/elasticsearch:<elasticsearch-version>

RUN bin/elasticsearch-plugin install --batch analysis-icu
```

Replace the placeholder with a specific Elasticsearch tag. Pin the image tag so every node runs the exact same server and plugin versions. When upgrading Elasticsearch, rebuild the image and verify plugin compatibility with the new version.

Do not manually install a plugin into one running container and update only a single node in the cluster. Heterogeneous nodes can cause index creation, document analysis, or shard recovery failures when analyzers depend on plugins.

## 7. Defining an analyzer using ICU

Once the plugin is installed on the nodes, you can define analyzers using the ICU tokenizer and ICU folding.

Example:

```json
{
  "settings": {
    "analysis": {
      "char_filter": {
        "vi_d_mapping": {
          "type": "mapping",
          "mappings": [
            "đ => d",
            "Đ => D"
          ]
        }
      },
      "analyzer": {
        "vi_icu_folded": {
          "type": "custom",
          "char_filter": [
            "vi_d_mapping"
          ],
          "tokenizer": "icu_tokenizer",
          "filter": [
            "icu_folding"
          ]
        }
      }
    }
  }
}
```

`icu_tokenizer` and `icu_folding` are only recognized when the plugin is installed on the nodes. Without the plugin, index creation requests will fail with an unrecognized tokenizer or token filter error.

You can test tokens:

```http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "vi_icu_folded",
  "text": [
    "Tiếng Việt",
    "Đà Nẵng",
    "Đặng Thị Hòa",
    "công nghệ thông tin"
  ]
}
```

Inspect the returned tokens and test with a representative query set. If ICU folding does not handle a particular case according to business rules, add character mappings or appropriate normalization steps rather than assuming the plugin handles every variation automatically.

## 8. Mapping analyzers in Spring Data Elasticsearch

Spring Data Elasticsearch declares index settings via the `@Setting` annotation or through separate index configuration. `@Field` attaches analyzers to document properties. Analyzers must exist in index settings before documents are indexed.

Example document using multi-field:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;
import org.springframework.data.elasticsearch.annotations.Setting;

@Document(indexName = "articles")
@Setting(settingPath = "/elasticsearch/articles-settings.json")
public class ArticleSearchDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(
            type = FieldType.Text,
            analyzer = "vi_sensitive",
            searchAnalyzer = "vi_sensitive"
        ),
        otherFields = {
            @InnerField(
                suffix = "folded",
                type = FieldType.Text,
                analyzer = "vi_folded",
                searchAnalyzer = "vi_folded"
            )
        }
    )
    private String title;

    @Field(type = FieldType.Text, analyzer = "vi_sensitive")
    private String content;

    // Constructors, getters and setters
}
```

In this example, `articles-settings.json` resides on the classpath at `src/main/resources/elasticsearch/articles-settings.json` and contains the matching `analysis` section. If choosing ICU analyzers, update analyzer names in the mapping and ensure the plugin is installed on all relevant nodes.

Creating the index and mapping with `IndexOperations` (exact APIs may vary across Spring Data versions):

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ArticleIndexInitializer {

    private final ElasticsearchOperations operations;

    public ArticleIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIndex() {
        IndexOperations indexOperations =
            operations.indexOps(ArticleSearchDocument.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
```

This snippet illustrates creating an index using settings and mappings bound to the document. In production systems, index initialization should be managed via migrations or deployment workflows to avoid concurrent index creation by multiple application instances and to control mapping versions.

### Searching both accented and unaccented text

With the multi-field mapping above, you can search across both the primary field and the folded subfield using `multi_match`:

```json
{
  "query": {
    "multi_match": {
      "query": "da nang",
      "fields": [
        "title^3",
        "title.folded"
      ],
      "type": "best_fields"
    }
  }
}
```

The `title` field has a higher boost to prioritize matches with accurate diacritics. The `title.folded` field helps match accented content when users type without diacritics. Tune boost weights using real data and search behavior; there is no universal boost ratio for every application.

If the user types `Đà Nẵng`, the query can likewise be analyzed across both fields. If the business requires strict distinction, apply a filter or separate search mode targeting the accent-sensitive field.

## 9. Vietnamese word segmentation at the application layer

If search requirements call for recognizing Vietnamese compound words, content can be preprocessed before indexing. A simple pipeline can produce two representations:

```text
Original text:
"Trường đại học công nghệ thông tin"

Display field:
"Trường đại học công nghệ thông tin"

Segmented field (illustrative example):
"trường_đại_học công_nghệ_thông_tin"
```

The segmented form comes from a dictionary-based segmenter; underscores here merely illustrate keeping multi-syllable phrases together as one token. The exact representation must follow the chosen library and remain consistent across both indexing and query analysis.

A document design can keep both the original field and the segmented field:

```json
{
  "title": "Trường đại học công nghệ thông tin",
  "title_segmented": "trường_đại_học công_nghệ_thông_tin",
  "title_folded": "truong dai hoc cong nghe thong tin"
}
```

Do not overwrite the display field with strings containing inserted delimiters. The original field must be preserved for display, highlighting, or accent-sensitive queries. The segmented field is a supplemental search representation.

### Keeping query-time analysis synchronized

The analyzer used at index time and the analyzer used at search time must be compatible. If the application preprocesses text with a segmenter at index time without applying the same logic at query time, query tokens may fail to match indexed tokens.

With `search_analyzer`, you can use a separate query configuration when there is a clear reason, but inspect `_analyze` output in both modes. A straightforward approach is applying the same segmentation and folding rules on both sides.

## 10. Synonyms and stop words in Vietnamese

Synonyms can improve search when users use alternate terms or variants. For example, a product may use `điện thoại` in content while users search for `smartphone`. You can configure a synonym filter or synonym set according to your Elasticsearch version's capabilities.

However, Vietnamese synonyms must be curated with context. One word can have multiple meanings; overly broad expansion adds noise. Decide which fields get synonyms, whether matching is accent-sensitive, and whether synonym updates must happen without reindexing.

Stop words also require caution. Function words such as `và`, `của`, `là`, `ở` appear frequently, yet stripping them can alter the meaning of proper nouns or search phrases. Build a stop word list only after measuring real queries and evaluating the impact on phrase queries.

## 11. Testing analyzers with a Vietnamese dataset

Do not test with only a single example like `tieng viet`. Create a test suite representative of input patterns and edge cases:

| Test category | Example | What to verify |
|---|---|---|
| Accented and unaccented | `tiếng Việt` / `tieng viet` | Folded field finds the document |
| Letter `đ` | `Đà Nẵng` / `da nang` | `đ` is handled according to policy |
| Uppercase | `ĐẶNG THỊ HÒA` / `đặng thị hòa` | Lowercasing does not drop or break tokens |
| Unicode NFC/NFD | `hòa` with equivalent decomposed form | Normalization causes no unintended mismatches |
| Tone marks | `ma`, `má`, `mà`, `mả`, `mã`, `mạ` | Accent-sensitive and folded fields behave as designed |
| Compound words | `học sinh`, `công nghệ thông tin` | Tokenizer/segmenter satisfies phrase queries |
| Punctuation | `Hà Nội, Việt Nam` | Tokenizer handles punctuation properly |
| Proper nouns | `Nguyễn Ái Quốc`, `Trần Đại Nghĩa` | Results do not suffer excessive noise |
| Mixed characters | `C++`, `Node.js`, product codes | Necessary symbols are not accidentally stripped |

Inspect tokens with `_analyze`, then test search results with real documents. Correct tokenization does not guarantee proper relevance; also evaluate result ordering, highlighting, phrase matching, and short queries.

## 12. Changing analyzers and reindexing

Analyzers affect tokens generated at index time. If you change the analyzer of a field that already holds data, updating settings does not automatically re-analyze old documents. Some analyzer settings can also only be set at index creation time.

When switching from `standard` to an ICU analyzer, adding a folded field, or changing word segmentation rules, you should:

1. Create a new index with the new settings and mapping.
2. Re-read source data or reindex appropriately.
3. Run the new analyzer against representative Vietnamese terms.
4. Compare token counts, query results, relevance ordering, and index size.
5. Sync updates occurring during backfill.
6. Switch the alias to the new index after verification.

Do not assume updating `@Field(analyzer = "...")` in code modifies the mapping of an existing index. The live index mapping and the mapping Spring Data expects may diverge; manage changes through an index migration process.

## 13. Choosing a solution by requirement

| Requirement | Starting solution | Plugin required? |
|---|---|---|
| Lowercasing only | `lowercase` | No |
| Basic accent-insensitive search | `asciifolding` and explicit mapping for `đ` if needed | No |
| Unicode normalization and ICU tokenizer | `icu_tokenizer`, `icu_folding`, `icu_normalizer` per configuration | Yes, `analysis-icu` |
| Dictionary-based Vietnamese compound-word segmentation | Vietnamese segmenter at application layer or evaluated specialized plugin | Depends on solution; ICU alone is insufficient |
| Both accented and unaccented search | Multi-field with accent-preserving field and folded field | Not required |
| Synonym search | Synonym filter/set and managed synonym data | Usually no separate plugin needed; depends on version features |

## 14. Conclusion

Vietnamese search requires explicit policies for tone marks, the letter `đ`, Unicode NFC/NFD, and word segmentation. `lowercase` handles letter casing, `asciifolding` supports basic accent-insensitive search, and `analysis-icu` adds general Unicode components when needed. ICU does not automatically perform dictionary-based Vietnamese word segmentation.

In Spring Data Elasticsearch, define analyzers in index settings, attach analyzers to fields or multi-fields via mappings, and verify tokens with `_analyze`. Keep an accent-sensitive field alongside a folded field to balance precision and unaccented searchability. Install plugins only when features require them; plugins must match the exact server version and be present on all relevant nodes. When compound words, synonyms, or deeper language processing are needed, add appropriate segmenters/dictionaries and apply the same logic at both index time and search time.
