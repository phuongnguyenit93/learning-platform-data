# Stop Words, Stemming, and Precision Trade-offs

When searching text, Elasticsearch does not necessarily compare the exact string a user types with the stored string. An analyzer can normalize text, split tokens, remove stop words, and reduce word variants to an approximate root form. These steps help users find documents even when query phrasing differs slightly from the stored data. However, each normalization step can also discard information and cause irrelevant documents to appear in results.

Two common techniques are **stop word removal** and **stemming**. Stop word removal eliminates words considered to contribute little to distinguishing documents. Stemming reduces morphological word variants to a common stem. Both can improve the search experience, but must be chosen based on language, data, and query intent.

## 1. Where does an analyzer process text?

### 1.1. Text analysis pipeline

An analyzer is a pipeline that processes a string into tokens for Elasticsearch to index or to analyze a query string. A custom analyzer typically has three groups of components:

1. **Character filters** process characters before tokenization, such as normalizing certain characters or replacing strings.
2. **Tokenizer** splits the string into tokens.
3. **Token filters** transform, remove, or enrich tokens after splitting.

Stop filters and stemmers are token filters. They run after the tokenizer, in the order declared in the analyzer.

~~~mermaid
flowchart LR
    A[Input text] --> B[Character filters]
    B --> C[Tokenizer]
    C --> D[Lowercase]
    D --> E[Stop filter]
    E --> F[Stemmer]
    F --> G[Tokens for indexing or query]
~~~

For example, the string:

~~~text
"The runners are running quickly"
~~~

can be processed in sequence:

- The tokenizer splits it into tokens such as `The`, `runners`, `are`, `running`, `quickly`.
- Lowercase converts tokens to lowercase.
- The stop filter removes words in the stop word list, such as `the` and `are`.
- The stemmer shortens remaining words according to the chosen stemming algorithm.

An illustrative result might look close to:

~~~text
["runner", "run", "quickli"]
~~~

This is an illustrative result for a specific English configuration; actual tokens depend on the tokenizer, stop-word list, and stemming algorithm. Stemming does not necessarily produce a valid dictionary word in English.

### 1.2. Analysis at index time and search time

Elasticsearch can analyze text at two stages:

- **Index-time analysis**: processes field content before writing tokens to the inverted index.
- **Search-time analysis**: processes query strings before matching against indexed tokens.

When a `text` field uses an analyzer, that analyzer is normally applied at index time. At search time, Elasticsearch uses `search_analyzer` if declared; otherwise, the search analyzer normally inherits the field's analyzer.

Both sides need to produce compatible tokens. If documents are indexed with stemming but queries are not stemmed, a query containing `running` may fail to match the stored token `run`. Conversely, if queries are stemmed while documents store the original form, the query token `run` may also fail to match the token `running`.

Therefore, when using stop filters or stemmers, explicitly design analyzers at both stages. You can use a separate analyzer for search if there is a specific reason, but verify that tokens produced by the query can still match tokens in the index.

## 2. What is a stop word?

### 2.1. The concept of stop words

Stop words are words that appear frequently and often contribute little to distinguishing documents in certain types of searches. In English, common examples include:

~~~text
a, an, the, is, are, of, in, on, and
~~~

In an English document collection, the word `the` appears in very many places. If the goal is topic-based search, this word typically contributes less than words such as `elasticsearch`, `index`, `mapping`, or `query`.

Stop words are not a one-size-fits-all list for every application. A word may be unimportant in general search yet critical in proper nouns, quotes, legal content, or specialized domain queries.

### 2.2. How does a stop filter work?

A stop filter checks tokens against a stop word list and removes tokens matching that list. Elasticsearch provides a `stop` token filter that can use a built-in list or an application-defined list.

Example English custom analyzer:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stop": {
          "type": "stop",
          "stopwords": "_english_"
        }
      },
      "analyzer": {
        "english_without_stop": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stop"
          ]
        }
      }
    }
  }
}
~~~

`_english_` is the built-in stop word list for English. It can be replaced with a custom list:

~~~json
{
  "type": "stop",
  "stopwords": ["a", "an", "the", "and"]
}
~~~

If you do not want to remove stop words, you can use `_none_` or omit the stop filter from the analyzer. Verify syntax and options against the documentation for your deployed Elasticsearch version.

### 2.3. Benefits of stop word removal

Removing stop words can bring several benefits:

- Reduces frequent tokens in the inverted index.
- Reduces noise from function words in multi-word queries.
- Helps queries focus more on content-bearing words.
- Can reduce indexed data size and processing cost in some workloads.
- Useful for search systems where users often type long sentences with many connecting words.

Actual impact depends on data and configuration. Elasticsearch already has scoring mechanisms and inverted index optimizations; do not assume removing stop words always makes the system faster or saves significant disk space. Measure on a representative dataset.

### 2.4. Risks of removing stop words

Stop words can carry critical meaning in a query. For example:

- `to be or not to be`: the word `not` changes the sentence meaning.
- `without sugar`: the word `without` specifies an exclusion condition.
- `state of the art`: the phrase can carry a specific meaning.
- Product names, organization names, or titles containing very common words.
- Legal, medical, or technical content, where a short word can alter meaning.

If negation words such as `not`, `no`, `without`, `không`, or `chưa` are removed, the system may return documents with the opposite meaning of what the user searched for.

Do not treat default stop word lists as absolute truth. Read the list, inspect real queries, and keep words with business meaning.

### 2.5. Token positions and phrase queries

When a stop filter removes a token, token position information can still be preserved via position increments. Consequently, the remaining words do not necessarily become adjacent as if the removed word never existed.

This affects `match_phrase` and position-based queries. For example, a query containing `state of the art` may be analyzed into the remaining tokens with corresponding position gaps. Phrase matching results depend on the analyzer at both index and search time.

For some applications needing exact phrase searches, test `_analyze` output and try `match_phrase` queries on representative data. Some applications may need a separate `search_quote_analyzer` to preserve function words when users search phrases enclosed in quotation marks.

## 3. What is stemming?

### 3.1. The concept of stemming

Stemming is the technique of reducing word variants to a common stem, typically by stripping or transforming suffixes. The goal is to allow related word forms to be found together.

Examples in English:

| Original word | Illustrative stem |
|---|---|
| `connect` | `connect` |
| `connected` | `connect` |
| `connecting` | `connect` |
| `connections` | `connect` |
| `running` | `run` |
| `runs` | `run` |

Exact results depend on the algorithm. A stem is not necessarily a complete word or a grammatically valid lemma.

When a document contains `connected` but a user searches for `connecting`, stemming can reduce both to the same token, helping the query find the document without enumerating every word variant.

### 3.2. Stemming vs. lemmatization

These two techniques are often confused:

| Criterion | Stemming | Lemmatization |
|---|---|---|
| Processing approach | Applies heuristic stripping/transformation rules | Identifies dictionary base form based on language and context |
| Output | Stem, which may not be a complete word | Lemma, usually a valid dictionary word |
| Grammatical context | Usually no deep analysis | May require part of speech and context |
| Cost | Typically lighter and simpler | May require dictionaries/language models |
| Example | `studies` may become `studi` under some algorithms | `studies` may become `study` |

Stemming fits cases needing fast morphological normalization where a degree of approximation is acceptable. Lemmatization fits cases requiring linguistic precision, though it typically requires specialized tools and higher processing cost.

Do not expect Elasticsearch stemmers to understand full grammar, part of speech, or sentence context.

### 3.3. The `stemmer` token filter in Elasticsearch

Elasticsearch provides the `stemmer` token filter. Example:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "english_stemmed": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stemmer"
          ]
        }
      }
    }
  }
}
~~~

Several algorithms or stemming variants can be chosen via corresponding language/filter configurations, such as Porter, Porter2, KStem, or light stemmers per language. Available choices and configuration names depend on the Elasticsearch/Lucene version; consult official documentation before use.

These choices generally represent trade-offs:

- Stronger stemmers merge more word variants, increasing the chance of finding related content.
- Lighter stemmers preserve more distinctions, reducing accidental over-merging.
- Dictionary-based stemmers can handle some word forms better than suffix-stripping rules, though still limited by language and vocabulary coverage.

### 3.4. Over-stemming and under-stemming

**Over-stemming** occurs when an algorithm collapses words with different meanings into the same stem. This can cause results to include irrelevant documents.

**Under-stemming** occurs when genuinely related variants fail to map to the same stem. Users may still miss some documents even when two words are morphologically related.

Illustrative examples:

- If a stemmer merges two unrelated words into the same token, queries may return both groups of documents.
- If a stemmer fails to recognize an inflected variant, searching with the other form may miss intended documents.

No stemming algorithm suits every language and dataset. Test on domain terminology, product names, proper nouns, abbreviations, and common user word forms.

## 4. Combining stop words and stemming

### 4.1. Token filter ordering

A stop filter and stemmer can appear together in the same analyzer. Declared order affects processing.

A common order for English is:

1. Lowercase to normalize letter case.
2. Stop filter to remove function words.
3. Stemmer to reduce remaining tokens.

Example:

~~~json
{
  "settings": {
    "analysis": {
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
        "english_catalog": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "english_stop",
            "english_stemmer"
          ]
        }
      }
    }
  }
}
~~~

The stop filter is typically placed before the stemmer because stop word lists are normally declared in readable unstemmed forms. If stemming runs first, tokens may be transformed before comparison with the stop word list, preventing expected removal.

When building custom analyzers, verify filter ordering with `_analyze` rather than merely reading the configuration and assuming the outcome.

### 4.2. Binding the analyzer to a field

An analyzer can be used at index time and search time:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "english_catalog",
        "search_analyzer": "english_catalog",
        "fields": {
          "raw": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

In this example:

- `title` is analyzed with `english_catalog` for full-text search.
- `title.raw` preserves the `keyword` value for whole-value matching or sorting/aggregations.
- `search_analyzer` is specified explicitly to clarify query analysis rules.

Multi-fields let an application search the same data in multiple ways. Users can perform full-text search on `title`, while exact matching operations use `title.raw`.

Note that the `keyword` subfield does not automatically apply stemming. This is helpful when original values must be preserved for exact comparison.

### 4.3. Separating stemmed and unstemmed fields

In some systems, the application needs both broad recall and stricter matching. You can create an additional `unstemmed` subfield with a lowercase-only analyzer, or use multi-fields according to an appropriate strategy.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "english_catalog",
        "fields": {
          "unstemmed": {
            "type": "text",
            "analyzer": "standard"
          },
          "raw": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

At query time, the application can combine multiple fields and boost appropriate fields. For instance, exact matches on the unstemmed field can be prioritized over matches that only align after stemming. Boost weights should be tested against real query sets; there is no fixed multiplier right for every system.

## 5. Precision and recall: accuracy trade-offs

### 5.1. What is precision?

Precision measures, among the documents the system returned, how many are genuinely relevant:

\[
Precision = \frac{\text{Relevant documents returned}}{\text{Total documents returned}}
\]

If the system returns 10 documents and only 8 are relevant, precision is 0.8 or 80%.

High precision means less noise in returned results. Users spend less time opening documents that do not fit their needs.

### 5.2. What is recall?

Recall measures, among all genuinely relevant documents in the dataset, how many the system found:

\[
Recall = \frac{\text{Relevant documents returned}}{\text{Total relevant documents existing}}
\]

If the dataset has 20 relevant documents and the system finds 15 of them, recall is 0.75 or 75%.

High recall means the system misses fewer relevant documents. This matters when users need comprehensive retrieval, such as searching case records, legal documents, or technical support knowledge bases.

### 5.3. Why do stop words and stemming affect precision/recall?

When an analyzer removes words or collapses multiple variants into the same stem, the set of matchable tokens changes.

| Adjustment | Potential impact | Risk |
|---|---|---|
| Remove common stop words | Reduces noise from low-discrimination words | Loses meaning if removed words are important |
| Keep stop words | Preserves sentence and phrase semantics | Increases frequent tokens, potentially making queries less focused |
| Aggressive stemming | Merges more variants, typically increasing findability | Falsely merges unrelated words, lowering precision |
| Light stemming | Preserves more distinctions, potentially reducing noisy matches | May miss some variants, lowering recall |
| No stemming | Preserves exact word forms in index | Users may need to type exact stored word forms |

These are common tendencies, not absolute rules. Real impact depends on the analyzer, query, data distribution, and relevance judgment criteria.

For example, a user searching `connect` may want documents containing `connected` and `connecting`. Stemming helps increase recall. However, if the stemmer merges unrelated terms as well, precision can drop.

Similarly, removing `without` from the query `products without sugar` can cause results to include products with sugar. In this case, stop word removal discards an important condition and search quality drops noticeably.

### 5.4. F1 score and other metrics

Precision and recall typically trade off against each other. You can use the F1 score to evaluate both together:

\[
F1 = 2 \times \frac{Precision \times Recall}{Precision + Recall}
\]

F1 is the harmonic mean of precision and recall. It drops when either metric is low.

In practical search, users care most about results at the top of the list. Therefore, also evaluate:

- **Precision@k**: proportion of relevant documents in the top k results.
- **Recall@k**: proportion of all relevant documents found in the top k results.
- **MRR**: rank position of the first relevant result across multiple queries.
- **NDCG**: ranking quality when results have graded relevance levels.

Do not optimize solely for F1 while ignoring ranking order. A system with good recall where important documents sit deep down the list can still deliver a poor experience.

## 6. Choosing stop words and stemmers by purpose

### 6.1. Not every field needs stemming

Fields generally serve different purposes:

| Field type | Typically suitable handling |
|---|---|
| Article body, long descriptions | Can use language-appropriate stop filter and stemming |
| Product names | Needs testing; keep an unstemmed or keyword field when needed |
| Product codes, SKUs | Usually `keyword` or an appropriate normalizer, no stemming |
| Emails, usernames | Usually custom normalization rules, no stemming |
| Statuses, category types | Usually `keyword` |
| Proper nouns, brand names | Be cautious with stop words and stemming |
| Legal content or quotations | Need to preserve negation words and meaningful phrases |

For instance, a stemmer is useful for long descriptions with rich morphological variation. Yet stemming an SKU code or brand name can corrupt the value meant for matching.

### 6.2. Protecting exceptions from stemming

Some terms must remain unchanged, such as brand names, abbreviations, or specialized terminology. You can use token filters like `keyword_marker` to mark tokens as protected from stemming, or `stemmer_override` to specify custom stem mappings.

Conceptual example:

~~~json
{
  "settings": {
    "analysis": {
      "filter": {
        "protected_terms": {
          "type": "keyword_marker",
          "keywords": ["elasticsearch", "spring"]
        },
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      },
      "analyzer": {
        "english_with_protected_terms": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "protected_terms",
            "english_stemmer"
          ]
        }
      }
    }
  }
}
~~~

Because `lowercase` runs before `keyword_marker`, the protected keywords list is also lowercase. Tokens marked as keywords are left intact by stemming filters that honor this mechanism.

`stemmer_override` lets you declare explicit stem rules, such as fixing the output for an exception word. These filters must be placed in the right order and verified on your Elasticsearch version.

### 6.3. Language is the decisive factor

Stop word lists and stemmers are language-dependent. Do not use an English list for Vietnamese or other languages. Nor can you assume an English stemmer handles proper nouns, compound words, or multilingual terminology well.

For multilingual data, identify content language or separate fields/indices by language where appropriate. Each data group may require its own analyzer.

If one field mixes multiple languages, a single analyzer rarely handles all cases optimally. Consider real-world requirements, dominant languages, and how users enter queries.

### 6.4. Special considerations for Vietnamese

Vietnamese has tone marks and word structures composed of multiple syllables separated by spaces. Syllable boundaries and word boundaries can differ: a single word may span multiple syllables, whereas a whitespace-splitting tokenizer does not necessarily produce tokens matching lexical units.

Therefore:

- Do not apply an English stop word list or English stemmer to Vietnamese content.
- Do not assume the `standard` tokenizer performs linguistic Vietnamese word segmentation.
- Check the actual tokenizers/analyzers and plugins available in your running Elasticsearch version.
- If high-quality Vietnamese search is required, evaluate appropriate word segmentation solutions, proper noun/term dictionaries, and diacritic handling.
- Be cautious when using ASCII folding to strip accents: two words with different meanings can become identical after normalization.
- Vietnamese stop words must be curated from real data and queries; do not mechanically strip negation words like `không`, `chưa`, `chẳng`.

For example, the words `học`, `học tập`, `học sinh` are semantically related but cannot be resolved properly merely by suffix stripping. A Vietnamese system may need word segmentation, synonyms, and suitable analyzers rather than a simple stemmer.

## 7. Testing analyzers with `_analyze`

### 7.1. Why use the Analyze API?

Before evaluating search results, inspect what tokens an analyzer produces. The Analyze API shows how an input string is split and transformed. This helps catch:

- Tokenizers splitting words unexpectedly.
- Important stop words being removed.
- Stemmers transforming words too aggressively or too weakly.
- Inappropriate token filter ordering.
- Casing or character normalization causing information loss.

Example:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "english_catalog",
  "text": "The runners are running quickly"
}
~~~

To see step-by-step details, use `explain`:

~~~http
POST /articles/_analyze
Content-Type: application/json

{
  "analyzer": "english_catalog",
  "text": "The runners are running quickly",
  "explain": true
}
~~~

The Analyze API is a token inspection tool; it does not prove final search results are correct. Search also depends on indexed documents, mappings, queries, scoring, and filters.

### 7.2. Check both index-time and search-time analyzers

If a field declares different `analyzer` and `search_analyzer` settings, test both. Query tokens must be compatible with tokens in the index.

For instance, a field might be indexed with stemming while the search analyzer does not stem. In that case, query word forms may fail to match stored stems.

Do not test an analyzer with only a single simple string. Test:

- Singular and plural forms.
- Verbs in multiple tenses.
- Words with prefixes/suffixes.
- Negation words.
- Proper nouns, brands, and technical terms.
- Sentences containing stop words in the middle.
- Quoted phrase queries.
- Abbreviations and domain symbols.

## 8. Evaluating quality with real query sets

### 8.1. Building an evaluation set

Create a set of queries representing how users actually search. Each query needs a predefined list of relevant documents or relevance labels assigned by evaluators.

Example evaluation table:

| Query | Document | Relevance |
|---|---|---:|
| `running shoes` | Article about running shoes | 3 |
| `running shoes` | Article about walking shoes | 2 |
| `running shoes` | Article about treadmills | 1 |
| `running shoes` | Unrelated article | 0 |

You can use a 0–3 scale:

- 0: not relevant.
- 1: marginally relevant.
- 2: fairly relevant.
- 3: highly relevant to the intent.

Labels should be consistent across evaluators. If the system only has binary relevant/not-relevant labels, precision and recall can be used; if graded relevance exists, also use NDCG.

### 8.2. Comparing configurations

Test at least the following configurations on the same query set:

1. Baseline analyzer without stop filter or stemming.
2. With stop filter, without stemming.
3. With stemming, without stop filter.
4. With both stop filter and stemming.
5. Lighter or stronger stemmers if supported by the language.

Keep the document set, queries, and scoring method constant across runs. Change only the analyzer so you know which factor caused result changes.

### 8.3. Measuring precision and recall

Suppose for a query, evaluators identify 10 relevant documents. Configuration A returns 8 documents, of which 7 are relevant:

- Precision = 7/8 = 87.5%.
- Recall = 7/10 = 70%.

Configuration B returns 12 documents, of which 9 are relevant:

- Precision = 9/12 = 75%.
- Recall = 9/10 = 90%.

Configuration B finds more relevant documents, but also introduces more noise. Configuration A returns cleaner results, but misses more documents.

Which is better depends on the product:

- Record lookup or compliance document search may prioritize recall.
- E-commerce search may prioritize precision in top results.
- Technical support search may need a balance of both metrics and strong ranking.
- Internal search systems may allow users to broaden queries when too few results appear.

### 8.4. Never evaluate on a single query

An analyzer may work well for some words yet fail on proper nouns, specialized terms, or negated phrases. Aggregate metrics across many queries and inspect key query segments individually.

Beyond aggregate metrics, manually review false positives (irrelevant results returned) and false negatives (relevant documents missed). These cases often reveal whether to refine the stop word list, stemmer, tokenizer, synonyms, or field boosting.

## 9. Common mistakes

**Using default stop word lists without inspection.** Default lists may strip words meaningful in your application domain. Review excluded words and test critical queries.

**Removing negation words.** Stripping `not`, `without`, `không`, or `chưa` can invert query meaning. Test negation queries explicitly.

**Applying stemming to every field.** Product codes, usernames, emails, statuses, and proper nouns generally require stricter rules. Stem only natural-language fields when there is a measured benefit.

**Misaligning index analyzer and search analyzer.** Queries can produce tokens that differ from stored tokens, leading to missed results.

**Assuming a stem is always a dictionary word.** A stemmer is a normalization algorithm, not a full grammatical analyzer.

**Confusing stemming and lemmatization.** The two techniques have different goals and linguistic depths.

**Ignoring phrase queries.** Stop filters can affect token positions and phrase matching behavior.

**Measuring only total result count.** More results do not equate to better search. Inspect relevance, precision, recall, and ranking order.

**Editing an analyzer on an existing index without accounting for old data.** Changing an analyzer or mapping may require creating a new index and reindexing so all documents are re-analyzed under the new rules.

## 10. Selection and tuning workflow

When designing an analyzer for a text field, follow this sequence:

1. Identify the field's language and data type.
2. Determine whether users need exact matching or content-based search.
3. Choose a tokenizer suited to the language.
4. Decide whether lowercasing, accent normalization, or other normalizations are needed.
5. Review stop words, especially negations and domain-specific terms.
6. Choose an appropriate stemmer or skip stemming if benefits are unclear.
7. Declare index-time and search-time analyzers consistently.
8. Use `_analyze` to inspect tokens.
9. Run a query set with relevance labels to measure precision, recall, and ranking quality.
10. Adjust one component at a time, re-measure, and save the selected configuration.

When changing an analyzer for a field with existing data, consider whether creating a new index and reindexing is needed. Elasticsearch does not automatically re-analyze all old data just because the application updated an analyzer definition.

## 11. Key takeaways

Stop word removal helps filter out frequent words but can discard important information. Stemming helps merge morphological variants but can falsely collapse unrelated words or miss related forms. Both are search quality decisions, not merely performance tuning knobs.

Choose based on language, field type, user needs, and empirical measurement. Use `_analyze` to understand tokens, verify phrase queries, and build a relevance-labeled query set to observe impacts on precision, recall, and ranking order. Only with empirical data do you have a solid basis to decide which stop words to drop, which stemmer to use, and which fields should stay in their original form.
