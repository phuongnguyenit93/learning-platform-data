# Edge N-Gram, N-Gram, and Index Size Cost

When building autocomplete or search-as-you-type functionality, an application often needs to match a document even when the user has only typed part of a word. Elasticsearch can support this requirement by generating additional shorter tokens from original tokens when indexing data. Two common techniques are **edge n-gram** and **n-gram**.

- **Edge n-gram** generates substrings anchored at the start of a token. It fits *prefix search*, such as a user typing `elas` to find `elasticsearch`.
- **N-gram** generates consecutive substrings at any position within a token. It can match a substring inside a word, such as `search` inside `elasticsearch`, but usually produces many more tokens.

Generating extra tokens makes search more flexible, yet increases the number of terms and postings stored in the inverted index. Therefore, choosing between edge n-gram and n-gram should be based on actual search behavior, word length, gram range, storage capacity, and indexing cost.

## 1. What is an n-gram?

An n-gram is a contiguous sequence of *n* units. In text search, the unit is usually a character. For example, for the token `spring`:

- 1-gram: s, p, r, i, n, g.
- 2-gram: sp, pr, ri, in, ng.
- 3-gram: spr, pri, rin, ing.

If a range from `min_gram` to `max_gram` is configured, the gram generator emits sequences with lengths in that range. With `min_gram = 2` and `max_gram = 3`, the token `spring` produces:

    2-gram: sp, pr, ri, in, ng
    3-gram: spr, pri, rin, ing

N-gram preserves contiguous character slices at every position in the token. Hence, a query can match a slice located at the beginning, middle, or end of a token if that slice was indexed.

N-gram does not understand word semantics. It merely emits character slices according to configuration. Grams may be fragments of a word rather than standalone words, so a character-level match is not necessarily semantically relevant.

## 2. What is an edge n-gram?

Edge n-gram also generates substrings, but only anchored at the first character of the token. With the token `spring`, `min_gram = 2`, and `max_gram = 5`, the result is:

    sp
    spr
    spri
    sprin

All of these sequences are prefixes of `spring`. Edge n-gram does not generate `pr`, `rin`, or `ing`, because they do not begin at the start of the token.

This property makes edge n-gram well suited for prefix-based autocomplete. As the user successively types `s`, `sp`, `spr`, or `spri`, each string can match a token generated when the document was indexed.

Example with the product name `Spring Data Elasticsearch`:

| Original token | Edge n-gram with min=2, max=5 |
|---|---|
| spring | sp, spr, spri, sprin |
| data | da, dat, data |
| elasticsearch | el, ela, elas, elast |

A user typing `elas` can find the document containing `elasticsearch`. A user typing `search` will not match via edge n-gram on that token, because `search` sits in the middle of the token rather than being a prefix.

## 3. How do n-gram and edge n-gram differ?

Suppose the original token is `spring`, configured with `min_gram = 2`, `max_gram = 3`.

| Technique | Generated grams |
|---|---|
| Edge n-gram | sp, spr |
| N-gram | sp, pr, ri, in, ng, spr, pri, rin, ing |

Edge n-gram only generates sequences starting from the beginning of the token. N-gram generates sequences at all possible positions.

| Criterion | Edge n-gram | N-gram |
|---|---|---|
| Starting position | Only at token start | At every position inside token |
| Suitable search type | Prefix, autocomplete | Substring at any position |
| Tokens generated | Usually fewer | Usually many more |
| Index size | Usually lower for the same gram range | Usually higher |
| Example | Typing `spr` finds `spring` | Typing `rin` finds `spring` |
| Use cases | Suggesting names, products, places by prefix | Finding substrings, codes, or mid-token character sequences |

If the requirement is only suggestions as the user types from the start of words, edge n-gram is usually the more sensible choice. If the requirement demands matching a substring in the middle of a token, n-gram may be needed, though at a higher cost.

## 4. Where does Elasticsearch generate grams in an analyzer?

Elasticsearch analyzes text through an analyzer. An analyzer typically consists of:

1. **Character filters:** can transform text before the tokenizer runs, such as replacing characters or stripping certain marks.
2. **Tokenizer:** splits text into tokens.
3. **Token filters:** transform, normalize, or generate additional tokens from tokenizer output.

Edge n-gram and n-gram can be used either as a tokenizer or as a token filter. The two forms differ in placement and behavior:

- **N-gram tokenizer / edge n-gram tokenizer:** splits the input directly into grams at the tokenizer stage. With the tokenizer, the `token_chars` setting can restrict which character classes are kept in tokens, such as keeping only letters and digits.
- **N-gram token filter / edge n-gram token filter:** receives tokens already produced by a tokenizer and generates grams from each token. This is convenient when you want to keep the word-splitting behavior of the `standard` tokenizer and only expand tokens afterward.

In common autocomplete examples, you can use the `standard` tokenizer to split sentences into words, then apply the `edge_ngram` token filter to each word.

With the text `Spring Data`, the tokenizer splits it into two tokens `Spring` and `Data`. The edge n-gram token filter generates prefixes separately for each token. It does not generate a gram spanning across the space between the two words.

## 5. Configuring edge n-gram for autocomplete

Suppose an application needs to search products by name prefix. We want to index prefixes from 2 to 10 characters long, while at search time analyzing user-entered keywords with a standard analyzer.

You can create the index with custom analyzers:

    PUT products
    {
      "settings": {
        "index": {
          "max_ngram_diff": 8
        },
        "analysis": {
          "filter": {
            "autocomplete_edge": {
              "type": "edge_ngram",
              "min_gram": 2,
              "max_gram": 10
            }
          },
          "analyzer": {
            "autocomplete_index": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "autocomplete_edge"
              ]
            },
            "autocomplete_search": {
              "type": "custom",
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
          "name": {
            "type": "text",
            "analyzer": "autocomplete_index",
            "search_analyzer": "autocomplete_search"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Here:

- `autocomplete_index` is used when indexing documents. It splits words with the `standard` tokenizer, lowercases letters, and generates prefixes from 2 to 10 characters.
- `autocomplete_search` is used when analyzing queries. It splits words and lowercases without generating additional grams.
- `search_analyzer` keeps the user's input keyword as a normal word, then matches it against prefixes already stored in the inverted index.
- `index.max_ngram_diff` permits the difference between `max_gram` and `min_gram` to be 8. Elasticsearch caps this difference to prevent unintentionally large gram configurations; set the setting appropriately for your chosen range.

Separating the index-time and search-time analyzers is crucial. If edge n-gram is used on both sides, an entered keyword also gets split into multiple prefixes, creating unintended matches and distorting relevance scores.

### Inspecting generated tokens

You can use the Analyze API to see how the analyzer behaves:

    POST products/_analyze
    {
      "analyzer": "autocomplete_index",
      "text": "Spring Data"
    }

With `min=2` and `max=10`, output includes prefix tokens of `spring` and `data` after lowercasing. For example, tokens for `spring` start with `sp`, `spr`, `spri` and continue through `spring`.

Test the search analyzer:

    POST products/_analyze
    {
      "analyzer": "autocomplete_search",
      "text": "Spri"
    }

The search analyzer emits token `spri`. This token can match the `spri` token indexed from `Spring`.

### Running queries

After indexing a document:

    POST products/_doc/1
    {
      "name": "Spring Data Elasticsearch",
      "category": "backend"
    }

You can search by prefix:

    GET products/_search
    {
      "query": {
        "match": {
          "name": "spri"
        }
      }
    }

The `match` query uses the search analyzer declared on the `name` field. It produces token `spri`, then looks up the matching token in the inverted index built by the edge n-gram analyzer.

In Spring Data Elasticsearch, the entity can declare the corresponding analyzers:

    @Document(indexName = "products", createIndex = false)
    public class Product {

        @Id
        private String id;

        @Field(
            type = FieldType.Text,
            analyzer = "autocomplete_index",
            searchAnalyzer = "autocomplete_search"
        )
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;
    }

Analyzer definitions must be supplied in index settings before creating the index. The annotation references analyzer names; it does not define the entire filter, tokenizer, and gram range configuration by itself. The example sets `createIndex = false` because the index and settings are created by a separate index management workflow.

## 6. Configuring n-gram for substring search

If an application needs to match a slice located in the middle of a token, an n-gram token filter can be used. For example, to find `ring` inside `spring`, edge n-gram does not generate `ring`, whereas n-gram does.

Example analyzer:

    PUT products_substring
    {
      "settings": {
        "index": {
          "max_ngram_diff": 8
        },
        "analysis": {
          "filter": {
            "substring_grams": {
              "type": "ngram",
              "min_gram": 2,
              "max_gram": 10
            }
          },
          "analyzer": {
            "substring_index": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "substring_grams"
              ]
            },
            "substring_search": {
              "type": "custom",
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
          "name": {
            "type": "text",
            "analyzer": "substring_index",
            "search_analyzer": "substring_search"
          }
        }
      }
    }

For token `spring`, the n-gram analyzer can produce `sp`, `pr`, `ri`, `in`, `ng` and longer grams like `spr`, `pri`, `rin`, `ing`. Thus, a query for `ring` can match the original token `spring` via indexed grams.

N-grams expand matching ability, yet can also broaden results more than desired. For instance, unrelated words may share the same short gram. The shorter the gram, the higher the overlap across words. Therefore, choose `min_gram` based on the shortest query length that has business meaning.

## 7. How is index size cost generated?

Elasticsearch stores terms in the inverted index to look up documents by term. When using n-grams, one original token is expanded into many small tokens. These tokens become indexable terms linked to the documents containing them.

If a token has length *L* and the gram configuration runs from *m* to *M*, the number of generated grams can be estimated as follows.

For edge n-gram:

\[
N_{edge} = \max(0,\min(M,L)-m+1)
\]

For full n-gram:

\[
N_{ngram} =
\sum_{k=m}^{\min(M,L)} (L-k+1)
\]

Where:

- L is the token length.
- m is `min_gram`.
- M is `max_gram`.
- k is the length of the gram being generated.

Example for a 10-character token with `min_gram = 2`, `max_gram = 5`:

- Edge n-gram generates 4 tokens: prefixes of lengths 2, 3, 4, and 5.
- N-gram generates 30 tokens: 9 grams of length 2, 8 grams of length 3, 7 grams of length 4, and 6 grams of length 5.

This is the number of token emissions for a single input token, not the number of unique terms or final byte size of the index. Actual size also depends on:

- Number of documents and original tokens.
- Number of unique terms after duplicate grams are merged in the dictionary.
- Term frequency and number of documents containing each term.
- Term length, postings structure, and compression ratio.
- Other index settings, segments, stored fields, and doc values.

Although exact disk usage cannot be derived from the token formula alone, emitted token count is a strong signal for comparing costs across configurations. Full n-gram typically generates many more token positions than edge n-gram, thus increasing inverted index size and indexing cost substantially.

## 8. Factors that increase or reduce cost

### `min_gram`

Lowering `min_gram` causes more short grams to be emitted. For example, `min=1` generates single characters. These grams typically appear across very many documents, producing large postings lists and making search results less selective.

Use single-character grams only if the product genuinely requires single-character search and you have evaluated the impact on storage, performance, and result quality.

### `max_gram`

Raising `max_gram` causes more long grams to be emitted. With edge n-gram, token count grows linearly with added lengths. With full n-gram, each new length also emits slices at multiple positions, so cost rises faster.

`max_gram` also affects searchability for long keywords. If an original token is longer than `max_gram`, the index analyzer does not emit an intact token at that length unless configured to preserve the original token. This can prevent long queries from matching as expected.

### Text length and number of fields

Documents with many words or multiple fields using n-grams emit many more tokens. Applying n-grams simultaneously to titles, descriptions, brand names, and long bodies can spike costs sharply.

Do not apply n-grams to all text fields by default. Restrict them to fields serving autocomplete or substring search.

### N-gram vs. edge n-gram

If only prefixes are needed, edge n-gram is usually more economical. If mid-word matching is required, n-gram may be necessary, but limit the gram range and field scope.

### Document count and update frequency

More documents mean more gram generation. When data is frequently updated or reindexed, CPU and I/O cost for token analysis also rises. Measure both indexing speed and search speed, not just final disk size.

## 9. `max_gram` and queries longer than indexed grams

Suppose the index analyzer only generates grams up to 10 characters long, yet a user enters a 13-character word. A regular search analyzer emits one 13-character token. If the index analyzer did not store the original token and did not generate grams longer than 10 characters, that long term may not exist in the inverted index. Consequently, the query fails to match even though the document contains the original word.

There are several ways to handle this:

1. Choose `max_gram` large enough for common query lengths.
2. Use the edge n-gram token filter with `preserve_original = true` if you need to keep the original token alongside prefixes.
3. Maintain a normal subfield to match full words, and combine it with the autocomplete field.
4. Switch to a different query or strategy for long queries.

Example preserving the original token:

    "filter": {
      "autocomplete_edge": {
        "type": "edge_ngram",
        "min_gram": 2,
        "max_gram": 10,
        "preserve_original": true
      }
    }

`preserve_original` can emit the original token in addition to the generated grams. This preserves whole-word matching beyond `max_gram`, while also increasing token count and storage. Verify behavior with the Analyze API on your exact Elasticsearch version.

Another approach is defining a multi-field: one field uses the autocomplete analyzer, and another uses a standard analyzer. That lets the application combine prefix matching and whole-word matching without forcing all queries through the same analyzer.

## 10. Choosing a configuration by search requirement

| Requirement | Configuration to consider | Reason |
|---|---|---|
| Suggestions as user types from word start | Edge n-gram | Only prefixes are needed |
| Matching character slice in middle of word | N-gram | Emits grams at all positions |
| Regular full-text search | `standard` analyzer or language-appropriate analyzer | No need to multiply tokens into grams |
| Suggestions from fixed weighted list | Completion suggester | Optimized for curated suggestion lists |
| Autocomplete on field with built-in support | `search_as_you_type` | Elasticsearch provides dedicated field type and subfields for search-as-you-type |
| Exact matching of codes or statuses | `keyword` and `term` query | No n-grams needed when not searching substrings |

Edge n-gram is not the default choice for every search problem. If you only need autocomplete from a curated suggestion list, the completion suggester may fit better. If you want search-as-you-type with structure managed by Elasticsearch, evaluate the `search_as_you_type` field type. If only exact matching is required, use `keyword` instead of generating extra grams.

## 11. Combining an autocomplete field and a regular search field

A product may need several search modes:

- Quick suggestions as the user types a name prefix.
- Full-text search by name.
- Exact filtering by category.
- Sorting or aggregations on appropriate fields.

Do not force a single field to satisfy every goal if its analyzer transforms tokens in incompatible ways. Multi-fields can be used:

    PUT products
    {
      "settings": {
        "index": {
          "max_ngram_diff": 8
        },
        "analysis": {
          "filter": {
            "autocomplete_edge": {
              "type": "edge_ngram",
              "min_gram": 2,
              "max_gram": 10
            }
          },
          "analyzer": {
            "autocomplete_index": {
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "autocomplete_edge"
              ]
            }
          }
        }
      },
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard",
            "fields": {
              "autocomplete": {
                "type": "text",
                "analyzer": "autocomplete_index",
                "search_analyzer": "standard"
              },
              "raw": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

In this example:

- `name` keeps the `standard` analyzer for full-text search.
- `name.autocomplete` uses edge n-gram for prefix queries.
- `name.raw` is a `keyword` for exact matching, sorting, or aggregations.

You can run autocomplete queries against the subfield:

    GET products/_search
    {
      "query": {
        "match": {
          "name.autocomplete": "spri"
        }
      }
    }

And full-text queries against the main field:

    GET products/_search
    {
      "query": {
        "match": {
          "name": "spring data"
        }
      }
    }

Multi-fields create additional indexed data for the same source value. This is an intentional trade-off: richer query capabilities come with higher storage and indexing costs.

## 12. Testing cost and quality before deployment

Do not pick `min_gram`, `max_gram`, or gram type based only on a couple of short examples. Test on representative data and measure the results.

### Step 1: inspect tokens

Use the Analyze API with short words, long words, accented words, numbers, hyphens, and multi-word phrases:

    POST products/_analyze
    {
      "analyzer": "autocomplete_index",
      "text": [
        "Spring Data",
        "Elasticsearch",
        "A12-B34",
        "Cà phê"
      ]
    }

Check:

- Does the tokenizer split words as intended?
- Do grams retain or strip characters as required?
- Are search keywords analyzed compatibly with indexed tokens?
- Do overly short or overly long words produce unexpected matches?

### Step 2: compare configurations

Create test indices with identical data:

- Standard analyzer.
- Edge n-gram with a narrow gram range.
- Edge n-gram with a wider gram range.
- N-gram with a corresponding gram range.

Never compare two indices that have different document counts or input data.

### Step 3: measure size

You can inspect index size with the CAT API:

    GET _cat/indices/products*?v&h=index,docs.count,store.size

Or use the stats API:

    GET products/_stats/store,indexing

Observe `store.size`, document count, indexing stats, and data indexing duration. Size should be measured after indexing and refresh complete under identical comparison conditions.

### Step 4: measure query quality and speed

Prepare a query set simulating user typing patterns:

- One character.
- First two or three characters.
- Longer prefixes.
- Mid-word character slices.
- Words with accents or special characters.
- Words longer than `max_gram`.

Measure latency, hit counts, result ordering, and proportion of results matching intent. A configuration generating many grams may match more documents while also increasing irrelevant results.

### Step 5: verify operations

Beyond disk size and latency, inspect:

- Bulk indexing throughput.
- Document update cost.
- Time required to reindex existing data.
- Segment sizes and merge overhead.
- Node heap, filesystem cache, and I/O.
- Query load when many users trigger autocomplete concurrently.

You cannot conclude a configuration is good from theoretical token counts alone. Use formulas for initial estimates, then measure on data and infrastructure close to production.

## 13. Common mistakes

### Using full n-gram when only prefixes are needed

N-gram creates grams at every position, inflating token counts without adding value if users only type from the start of words. For prefix-based autocomplete, edge n-gram is usually more economical.

### Choosing `min_gram` too small

One- or two-character grams can occur in very many words. Results become overly broad, many documents match simultaneously, and postings costs rise. Choose `min_gram` based on meaningful query lengths, not merely to match as few typed characters as possible.

### Choosing `max_gram` too low

Keywords longer than the maximum gram length may fail to match if original tokens are not preserved. Test long queries and consider `preserve_original` or a standard search field.

### Using the same analyzer for index and search

If the search analyzer also emits n-grams, the query gets split into many grams, altering matching semantics and relevance scores. For prefix autocomplete, usually generate grams at index time and use a standard analyzer at search time.

### Applying n-grams to every field

N-grams on long description fields, large bodies, or many fields at once can cause index size to balloon. Apply them only to fields genuinely requiring prefix or substring search.

### Failing to inspect tokenizer and `token_chars`

With an n-gram tokenizer, `token_chars` controls which character types are kept. If unchecked, spaces, punctuation, or special characters can emit unwanted grams. With a token filter, check how the preceding tokenizer split the text.

### Assuming more grams only make the index larger

More grams also impact indexing throughput, merges, caches, query selectivity, and relevance scores. Common grams can widen queries and increase processing work.

## Conclusion

Edge n-gram emits token prefixes and fits prefix-based autocomplete. N-gram emits substrings at every position, supporting mid-word matching but typically generating far more tokens. Increased token counts add terms and postings to the inverted index, raising storage, indexing, and operational costs.

When designing, clarify whether users need prefix or substring matching, choose `min_gram` and `max_gram` based on real queries, configure compatible index and search analyzers, and measure storage and performance on representative data. If you only need autocomplete, edge n-gram is usually a sensible starting point; if substring search is required, constrain n-gram scope and evaluate carefully so index cost does not outweigh search benefits.
