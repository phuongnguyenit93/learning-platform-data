# Search-as-you-type, Edge N-gram, and Choosing Based on Requirements

A search box often needs to respond immediately while the user is typing, before they finish a word or phrase. If an application only runs a match query on full terms, a half-typed keyword may not match indexed tokens yet. Elasticsearch offers several ways to solve this problem, two common options being the search_as_you_type field type and an analyzer using edge n-gram.

Both approaches support prefix searching, yet they organize the index and handle queries differently:

- **search_as_you_type** is a dedicated Elasticsearch field type. It automatically creates sub-fields for phrase and prefix searching, typically queried using multi_match with type bool_prefix.
- **edge n-gram** is a text analysis technique. At index time, an analyzer generates prefix tokens from the start of each word. Applications can customize min_gram, max_gram, analyzers, and queries to fit specific requirements.

Beyond these two options, Elasticsearch also provides match_phrase_prefix, prefix query, and completion suggester. Choose a solution based on the nature of the data and the experience to build: full-text search while typing, suggesting names from a list, looking up identifiers, or autocompleting a phrase.

## 1. The Challenge of Searching While the User Types

Suppose a document has a title:

    Spring Data Elasticsearch Guide

As the user types step by step:

    s
    sp
    spr
    spri
    spring
    spring d
    spring da

The application wants to show matching results even when the last word is incomplete. An ordinary match query analyzes the query into tokens and looks up corresponding terms in the inverted index. If the indexed token is spring while the user is typing spri, the two terms are not identical, so a regular match may fail to find the document.

Search-as-you-type solves this by preparing index data to support prefixes. Depending on the solution, Elasticsearch can match the prefix of the last token, combine completed words, or prioritize results with matching word order.

A search-as-you-type box may need to:

- Match words at the start of a title.
- Match the prefix of the last word.
- Allow previously typed words to appear in appropriate positions.
- Prefer results whose phrase matches the order the user typed.
- Maintain low latency when document counts are large.
- Support diacritics, casing, and the language of the data.

Not every use case needs the exact same semantics. For example, product name autocomplete may need suggestions by name prefix; full-text search may need multi-field matching and relevance ranking; SKU lookup may only need prefix matching on a keyword field.

## 2. Overview of Options

| Approach | How It Works | Best Fit When |
|---|---|---|
| search_as_you_type | Elasticsearch creates shingle and prefix sub-fields to support phrases being typed | Wanting full-text search-as-you-type with relatively simple setup |
| edge n-gram | Indexes multiple prefixes of each token | Needing control over min/max gram, analyzer, or custom prefix logic |
| match_phrase_prefix | Searches phrases, treating the final term as a prefix | Needing ordered phrases where data is not huge or latency is measured acceptable |
| prefix query | Finds terms starting with a string on a suitable field | Exact prefix lookup on keyword fields or identifiers |
| completion suggester | Uses a dedicated completion structure to return suggestions | Suggesting from a pre-prepared list of choices like product names or places |

There is no single option that is always best. search_as_you_type is usually a reasonable starting point for full-text search boxes. Edge n-gram is useful when fine-grained control over prefix tokens is needed. Completion suggester fits curated suggestion lists, while prefix query fits keyword fields and codes.

## 3. What Is search_as_you_type?

search_as_you_type is an Elasticsearch field type designed for searching while the user types. When mapping this field, Elasticsearch creates several sub-fields to support phrase and prefix search:

- The root field stores content as text.
- Shingle sub-fields like _2gram and _3gram store adjacent token groups.
- The _index_prefix sub-field supports efficient prefix queries and is used by Elasticsearch in the corresponding search mechanism.

Example mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "search_as_you_type"
          }
        }
      }
    }

With the mapping above, Elasticsearch creates the required sub-fields for name. The application does not need to manually define an edge_ngram analyzer for the basic case.

You can configure max_shingle_size to control the largest shingle size:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "search_as_you_type",
            "max_shingle_size": 3
          }
        }
      }
    }

The default value is usually 3; Elasticsearch supports shingle sizes within the range specified in your version's documentation. Increasing shingle size can improve consecutive multi-word matching, while also increasing indexed data volume.

### Generated Sub-fields

For a field named name, the sub-fields usually take the form:

    name
    name._2gram
    name._3gram
    name._index_prefix

The root field supports token search. The shingle fields store adjacent token groups, helping boost phrases in order. The _index_prefix field supports prefixes of the final token and is used by Elasticsearch to optimize prefix queries on search_as_you_type fields.

In typical queries, applications usually only need to specify name, name._2gram, and name._3gram. You do not need to manually add _index_prefix to the fields list in every case; the prefix sub-field mechanism is designed to support the corresponding queries automatically.

## 4. Querying search_as_you_type with bool_prefix

Elasticsearch typically uses multi_match with type bool_prefix to search across a search_as_you_type field and its shingle sub-fields.

Example:

    GET products/_search
    {
      "query": {
        "multi_match": {
          "query": "spring data elas",
          "type": "bool_prefix",
          "fields": [
            "name",
            "name._2gram",
            "name._3gram"
          ]
        }
      }
    }

bool_prefix builds a match_bool_prefix query on each field and combines the results. Terms before the last term are treated as ordinary terms; the last term is treated as a prefix. The shingle sub-fields help the query rank results with multiple consecutive words in order higher.

For example:

- A document with name Spring Data Elasticsearch Guide can match the query spring data elas.
- A document with name Elasticsearch Guide for Spring Data may still match terms depending on the operator and query structure, but usually does not receive the same priority for a leading consecutive sequence.
- A document containing only the word spring without the remaining terms will not satisfy a query requiring all terms.

To require all terms in the query to match, configure operator AND:

    GET products/_search
    {
      "query": {
        "multi_match": {
          "query": "spring data elas",
          "type": "bool_prefix",
          "operator": "and",
          "fields": [
            "name",
            "name._2gram",
            "name._3gram"
          ]
        }
      }
    }

The operator controls how terms are combined in match_bool_prefix. Test with representative data to decide whether the application should accept documents missing a term or require all entered words to match.

## 5. Why Does search_as_you_type Use Shingles?

Shingles are groups of adjacent tokens generated from a string. Example text:

    spring data elasticsearch guide

Two-word shingles may include:

    spring data
    data elasticsearch
    elasticsearch guide

Three-word shingles may include:

    spring data elasticsearch
    data elasticsearch guide

By indexing these phrases, Elasticsearch can recognize multiple consecutive words and prioritize documents whose word order is closer to the query. This is why querying _2gram and _3gram fields typically yields better ranking than searching individual tokens alone.

Shingles do not mean Elasticsearch only matches exact verbatim phrases. Queries can still combine multiple fields and tokens under bool_prefix semantics. Shingles act as an additional signal for ranking and phrase matching.

With a larger max_shingle_size, the index can hold more token combinations. Balance index size, ingest speed, and actual relevance benefit.

## 6. search_as_you_type in Spring Data Elasticsearch

In modern Spring Data Elasticsearch, you can use NativeQuery and the Elasticsearch Java API Client to build a multi-match bool_prefix query.

Example entity:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        private String description;
    }

The search_as_you_type mapping should be created consistently with the entity. Mappings can be managed via index templates, index initialization scripts, or IndexOperations in Spring Data. How annotations declare each FieldType depends on your Spring Data Elasticsearch version; check your project's API version instead of assuming annotations support every Elasticsearch mapping property.

Search service:

    @Service
    public class ProductSuggestService {

        private final ElasticsearchOperations operations;

        public ProductSuggestService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> suggest(
                String input,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .multiMatch(m -> m
                        .query(input)
                        .type(TextQueryType.BoolPrefix)
                        .fields(
                            "name",
                            "name._2gram",
                            "name._3gram"
                        )
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

Key imports:

    import co.elastic.clients.elasticsearch._types.query_dsl.TextQueryType;
    import org.springframework.data.domain.Pageable;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
    import org.springframework.data.elasticsearch.core.SearchHits;

In this example:

- input is the string the user is typing.
- TextQueryType.BoolPrefix selects multi_match bool_prefix.
- name is the root field.
- name._2gram and name._3gram are sub-fields automatically created by Elasticsearch.
- Pageable limits the number of returned suggestions.
- ElasticsearchOperations executes the query and maps results to Product.

Enum names and builder signatures depend on the Elasticsearch Java API Client version used by Spring Data. If your project version lacks the exact enum or overload shown, check your actual dependencies and use the corresponding API.

## 7. What Is Edge N-gram?

Edge n-gram is a technique for generating prefix tokens starting from the beginning of each original token. For example, from elasticsearch with min_gram = 2 and max_gram = 6, it can produce:

    el
    ela
    elas
    elast
    elasti

When the user types ela, documents containing the token elasticsearch can be found because the ela token was indexed.

How it differs from regular n-grams:

- Edge n-gram only generates sequences starting from the beginning of a token.
- N-gram can generate substrings at any position within a token.

For example, from keyboard:

- Edge n-gram can produce ke, key, keyb, keybo...
- N-gram of length 3 can produce key, e y b (without spaces), ybo, boa... depending on configuration and tokenization.

For prefix-based autocomplete, edge n-gram is usually better suited than general n-grams because users typically type left-to-right from the start of a word.

## 8. edge_ngram Tokenizer and Token Filter

Elasticsearch can generate edge n-grams using a tokenizer or a token filter. A common setup uses a standard tokenizer to split words, followed by an edge_ngram token filter to create prefixes for each token.

Example:

    PUT products
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
            "name_autocomplete_index": {
              "type": "custom",
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "name_edge_ngram"
              ]
            },
            "name_autocomplete_search": {
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
            "analyzer": "name_autocomplete_index",
            "search_analyzer": "name_autocomplete_search"
          }
        }
      }
    }

Here:

- standard tokenizer splits text into tokens.
- lowercase normalizes letter casing.
- name_edge_ngram creates prefixes at index time.
- search_analyzer only lowercases, without re-creating n-grams during search.

Separating index and search analyzers is critical. The index needs prefixes stored so they can be found; the query should be analyzed into normal tokens. If the search analyzer also creates edge n-grams, queries can be expanded into multiple prefixes, altering semantics and yielding overly broad results.

## 9. Why Separate the Index Analyzer and Search Analyzer?

Suppose a document has:

    name = Elasticsearch

With an edge n-gram index analyzer where min_gram = 2, max_gram = 6, the token stream may contain:

    el
    ela
    elas
    elast
    elasti

When the user types:

    elas

The search analyzer normalizes it to a single token elas. That term exists in the inverted index, so the document matches.

If the search analyzer also generated edge n-grams, the query elas could turn into:

    el
    ela
    elas

This is unnecessary for basic prefix queries and increases the number of terms searched. More importantly, if a query is longer than max_gram, the input token may fail to match indexed tokens as intended.

Common rule of thumb:

- Index analyzer: generates prefix tokens.
- Search analyzer: normalizes queries while keeping full tokens.

Specialized designs may use different search-time analyzers, but semantics must be clearly defined and tested on real data.

## 10. Choosing min_gram and max_gram

Two key parameters of edge_ngram:

- min_gram: minimum length of generated prefixes.
- max_gram: maximum length of generated prefixes.

For example, min_gram = 2, max_gram = 5 on token keyboard:

    ke
    key
    keyb
    keybo

If min_gram = 2, a single-character query k has no matching token in the index and may return no results. If min_gram = 1, users get suggestions from the very first character, though indexed token count grows and results can be very broad.

max_gram caps the length of stored prefixes. If max_gram = 15 but the user types a 20-character token, the full token may not exist in the edge n-gram index. When the query analyzer preserves the 20-character token, the query may fail to match.

Ways to handle this:

- Pick max_gram large enough for realistic word lengths.
- Use a multi-field with an ordinary full-text field to match full tokens.
- Combine an appropriate prefix query for cases longer than max_gram.
- Only use a truncate token filter at search time when false-positive risks are well understood.

Do not set max_gram excessively large just to cover every edge case. More prefixes increase index size and indexing cost.

### Estimating Token Count

For a token of length L, min_gram m, and max_gram M, the number of generated prefixes is approximately:

    max(0, min(L, M) - m + 1)

For example, a 12-character token with min_gram = 2 and max_gram = 8 produces around 7 prefixes. A document with many tokens and multiple edge n-gram fields will grow indexed term counts rapidly.

## 11. Querying Edge N-gram Fields

With the edge n-gram mapping above, a match query can be used:

    GET products/_search
    {
      "query": {
        "match": {
          "name": {
            "query": "elas",
            "operator": "and"
          }
        }
      }
    }

The search analyzer normalizes elas into a single complete token. That token matches the prefix token indexed from Elasticsearch.

If the query contains multiple words:

    GET products/_search
    {
      "query": {
        "match": {
          "name": {
            "query": "spring data elas",
            "operator": "and"
          }
        }
      }
    }

The words spring and data must also exist as indexed prefix tokens; elas can match the prefix of elasticsearch. Depending on requirements, you can design a multi-field where completed words are matched with a standard analyzer while the last word uses prefix semantics.

### Edge N-gram and Word Order

Edge n-gram generates prefixes per token; it does not automatically enforce full-phrase word order. A match query on the field can match terms in various positions without requiring them to form an ordered phrase.

If word order matters, you can:

- Combine the edge n-gram field with a regular text field.
- Use a bool query to boost match_phrase on a standard field.
- Use search_as_you_type with shingle sub-fields.
- Use phrase_prefix if phrase semantics fit.

Do not assume edge n-gram provides full phrase ranking on its own.

## 12. Separating Autocomplete Fields and Full-Text Fields

In many applications, the same content serves two goals:

1. Regular searching after the user submits a form.
2. Suggestions while the user is typing.

A multi-field can index both ways:

    PUT products
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
            "autocomplete_index": {
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "name_edge_ngram"
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
          "name": {
            "type": "text",
            "analyzer": "standard",
            "fields": {
              "autocomplete": {
                "type": "text",
                "analyzer": "autocomplete_index",
                "search_analyzer": "autocomplete_search"
              },
              "keyword": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

Then:

- Use name for full-text matching.
- Use name.autocomplete for queries while typing.
- Use name.keyword for exact matching, sorting, or aggregations.

This design keeps each field's semantics clear. However, every multi-field increases index size and write cost; only create variants that the application actually uses.

## 13. Combining Autocomplete and Full-Text Relevance

A good search experience rarely relies on prefixes alone. Once the user has typed full words, full-text relevance can matter more than mere prefix matching.

A bool query can be used:

    GET products/_search
    {
      "query": {
        "bool": {
          "should": [
            {
              "multi_match": {
                "query": "spring data elas",
                "type": "bool_prefix",
                "fields": [
                  "name",
                  "name._2gram",
                  "name._3gram"
                ],
                "boost": 3
              }
            },
            {
              "match": {
                "description": {
                  "query": "spring data elasticsearch",
                  "boost": 1
                }
              }
            }
          ],
          "minimum_should_match": 1
        }
      }
    }

In this example, search_as_you_type provides the primary signal for product names, while description adds full-text results. Boosts tune relative priority.

With edge n-gram, you can combine a match on name.autocomplete with a match on standard name or description. Avoid creating two nearly identical clauses if they add no value.

## 14. match_phrase_prefix: A Simple Choice for Phrases

match_phrase_prefix matches phrases in order and allows the final term to act as a prefix. Example:

    GET products/_search
    {
      "query": {
        "match_phrase_prefix": {
          "name": {
            "query": "spring data elas",
            "max_expansions": 20
          }
        }
      }
    }

This query suits cases where the user types a phrase and word order matters. max_expansions limits how many prefixes are expanded for the last term.

Advantages:

- Simple syntax.
- Does not necessarily require creating an edge n-gram field.
- Clear phrase semantics.

Limitations:

- Query-time prefix expansion can be costly.
- Only the last term is treated as a prefix in the phrase.
- Requires benchmarking with large datasets and realistic term counts.

If the requirement is search-as-you-type with good relevance and optimization at scale, search_as_you_type or edge n-gram usually allows pre-building index data for faster queries.

## 15. Prefix Query for Identifiers and Keywords

Not every search box needs a text analyzer. For SKUs, order codes, or normalized usernames, a prefix query on a keyword field may fit better.

Mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "sku": {
            "type": "keyword"
          }
        }
      }
    }

Query:

    GET products/_search
    {
      "query": {
        "prefix": {
          "sku": {
            "value": "KB-10"
          }
        }
      }
    }

Prefix query finds terms starting with the specified string. It does not split strings into words and does not run an analyzer like match queries.

With keyword fields, clearly define casing and normalize codes at index time and query time. A normalizer can be used for keyword if semantics require it.

Prefix queries on fields with many terms or large datasets may require benchmarking. Do not replace every prefix use case with a wildcard query starting with *; leading wildcards are usually harder to optimize.

## 16. Completion Suggester for Curated Suggestion Lists

Completion suggester is a specialized mechanism for autocomplete when the application has a pre-prepared list of suggestions, such as:

- City names.
- Brand names.
- Popular categories.
- Curated product names.
- Common search keywords.

Mapping:

    PUT search_suggestions
    {
      "mappings": {
        "properties": {
          "suggest": {
            "type": "completion"
          },
          "category": {
            "type": "keyword"
          }
        }
      }
    }

Index document:

    PUT search_suggestions/_doc/1
    {
      "suggest": {
        "input": [
          "Spring Data Elasticsearch",
          "Spring Elasticsearch"
        ],
        "weight": 10
      },
      "category": "technology"
    }

Query:

    POST search_suggestions/_search
    {
      "suggest": {
        "name-suggest": {
          "prefix": "spring data el",
          "completion": {
            "field": "suggest"
          }
        }
      }
    }

Completion suggester uses a specialized data structure to return prefix suggestions. It fits a set of choices indexed into a completion field, and does not replace full-text search across arbitrary document content.

Weights can be used to rank suggestions. If contextual filtering is needed, completion suggester supports context suggesters per mapping configuration. Check limits and operational characteristics of completion fields for your Elasticsearch version.

## 17. Choosing search_as_you_type vs. Edge N-gram?

Both options support prefixes but offer different degrees of customization:

| Criterion | search_as_you_type | edge n-gram |
|---|---|---|
| Initial setup | Simple, dedicated field type | Must define custom analyzers |
| Sub-fields | Elasticsearch automatically creates shingle and index-prefix fields | Application defines multi-fields manually if needed |
| Typical query | multi_match bool_prefix | match on edge n-gram field, combinable with other queries |
| Control over min/max gram | Not direct like edge n-gram analyzer | Yes |
| Word order optimization | Built-in shingle sub-fields | Must combine separate fields/queries |
| Analyzer customization | Limited by field type design | Flexible |
| Index footprint | Increases due to sub-fields | Increases with prefix count and field count |
| Best fit | Common full-text search-as-you-type | Custom prefix rules or fine-grained tuning |

Start with search_as_you_type when:

- Searching across multi-word titles or names.
- Wanting prefix support for the final term.
- Wanting shingles to improve phrase ordering.
- Not needing direct control over min_gram/max_gram.

Consider edge n-gram when:

- Needing to specify exact minimum/maximum prefix lengths.
- Applying the same technique to specialized fields or analyzers.
- Needing control over normalization, tokenization, or separate multi-fields.
- Having relevance requirements and benchmarks proving custom settings perform better.

## 18. Choosing Based on Product Requirements

Typical scenarios:

| Requirement | Option to Try First | Reason |
|---|---|---|
| Searching product names while typing | search_as_you_type | Built-in shingle and prefix sub-fields |
| Searching ordered phrases with incomplete final word | match_phrase_prefix or search_as_you_type | Preserves phrase semantics |
| Prefix lookup on SKU or order code | prefix on keyword | Codes usually need exact prefix matching |
| Suggesting from a list of cities/brands | completion suggester | Curated suggestion data |
| Need custom min_gram/max_gram | edge n-gram | Direct analyzer control |
| Multi-field search ranked by relevance | multi_match combining appropriate fields | Can blend prefix and full-text matching |
| Multilingual search with dedicated analyzers | Language-specific analyzers/multi-fields | Need control over stemming, folding, and tokenization |

Clarify whether the user is searching for a document or picking a suggestion. Completion suggester usually fits selecting a value from a list; search_as_you_type and edge n-gram fit better when results are full-text documents.

## 19. Multilingual Search and Normalization

Search-as-you-type depends on analyzers. For Vietnamese data, consider how the tokenizer segments words, Unicode normalization, diacritics, and product search rules.

Questions to verify:

- Should accented and unaccented text match each other?
- Is lowercasing needed?
- Is ASCII folding or a custom Vietnamese diacritic converter needed?
- Does the tokenizer segment Vietnamese words as expected?
- Are separate analyzers needed per language?
- Are proper nouns, product codes, or abbreviations analyzed improperly?

Lowercasing does not strip Vietnamese diacritics. ASCII folding can convert some accented characters to unaccented forms, yet analyzer settings and real results must be tested against Vietnamese data.

Do not apply the exact same analyzer to every field. Product names, SKUs, long descriptions, and person names may require different mappings.

### Testing with the Analyze API

Before deploying, inspect actual tokens:

    POST products/_analyze
    {
      "analyzer": "name_autocomplete_index",
      "text": "Keychron Mechanical Keyboard"
    }

With the search analyzer:

    POST products/_analyze
    {
      "analyzer": "name_autocomplete_search",
      "text": "keychron mech"
    }

Compare the two token streams to confirm:

- Index analyzer generates the expected prefixes.
- Search analyzer does not generate unwanted n-grams.
- Diacritics and casing are handled as required.
- min_gram and max_gram do not drop valid queries.

## 20. Performance and Index Size

Autocomplete typically trades index size and indexing cost to reduce query-time work.

With edge n-gram, every original token produces multiple prefix tokens. With low min_gram and high max_gram, token counts grow. Applied across multiple fields or languages, inverted index size can increase substantially.

With search_as_you_type, shingle and prefix sub-fields also increase indexed data compared to a plain text field. Elasticsearch manages those structures, yet applications still must measure storage and throughput.

A few guidelines:

- Only enable autocomplete on fields that truly need it.
- Cap max_gram based on realistic query lengths.
- Choose min_gram based on the minimum character count where the product wants to display suggestions.
- Keep page sizes small for suggestion endpoints.
- Debounce on the client so requests are not sent on every keystroke if latency and load do not allow it.
- Cap concurrent requests and apply timeouts.
- Monitor p95/p99 latency, CPU, heap, and index size.
- Benchmark with data whose word distributions and lengths mirror production.

Do not benchmark just one query against a handful of documents. Short prefixes typically match many documents and are the most critical case to benchmark.

## 21. Debouncing and Suggestion Endpoint Design

Even when Elasticsearch queries are fast, sending a request on every keystroke can create heavy load. Frontends typically use debouncing to wait briefly after the last keystroke before sending a request.

Suggestion flow:

    User types a character
          |
          v
    Reset debounce timer
          |
          v
    Timer expired?
          |
          +-- No --> Keep waiting
          |
          +-- Yes --> Send suggestion request
                         |
                         v
                    Elasticsearch
                         |
                         v
                    Return top N
                         |
                         v
                    Display suggestions

On the server:

- Reject or ignore overly short queries if business rules require.
- Cap result size.
- Allowlist fields and filters.
- Apply authorization/tenant filters just like other search endpoints.
- Enforce processing timeouts.
- Do not return excessive metadata if the UI only needs id and label.

Debouncing is a client-side optimization; it does not replace server-side load limits and resource protection.

## 22. Reindexing When Changing Analyzers or Mappings

Analyzers run when documents are indexed. If you change min_gram, max_gram, tokenizers, or filters, already-indexed tokens are not regenerated automatically simply by updating settings.

Many mapping and analyzer properties cannot be altered in place on an existing field. When changing an analyzer or switching a field to search_as_you_type, the standard procedure is:

1. Create a new index with the new settings and mappings.
2. Reindex documents from the old index into the new index.
3. Verify document counts and sample queries.
4. Switch the alias to the new index once data is ready.
5. Keep a rollback plan to the old index per operational procedures.

Example creating a new index:

    PUT products_v2
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
            "name_autocomplete_index": {
              "tokenizer": "standard",
              "filter": [
                "lowercase",
                "name_edge_ngram"
              ]
            },
            "name_autocomplete_search": {
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
            "analyzer": "name_autocomplete_index",
            "search_analyzer": "name_autocomplete_search"
          }
        }
      }
    }

After reindexing and verification, the alias can be switched to the new index using an atomic alias update request. Exact alias switching steps depend on alias names and the application's deployment process.

## 23. Testing Autocomplete Quality

A syntactically valid autocomplete query does not guarantee a good user experience. Prepare a representative query suite:

| Query Being Typed | Expected Results |
|---|---|
| spr | Spring Data Elasticsearch |
| spring d | Spring Data Elasticsearch |
| spring data el | Spring Data Elasticsearch |
| key | Keyboard, Keychron |
| KB-10 | Product codes with prefix KB-10 |
| ban phim | Products with names matching diacritic policy |

For each query, check:

- Do relevant documents appear?
- Are results in the desired word order?
- Can the final word be incomplete?
- Does a single-character query return too many results?
- Do queries longer than max_gram work?
- Do accented and unaccented names meet requirements?
- Are there wrong matches caused by analyzers or fields?
- Is latency stable on popular prefixes?

Measure both relevance and performance. For autocomplete, the ordering of the top 5 or top 10 results usually matters more than getting an exact total document count. Suggestion endpoints may not need total hits.

## 24. Common Pitfalls

### Using Regular match for Incomplete Final Tokens

Match queries do not automatically treat the final token as a prefix. If the user types elas while the document has elasticsearch, use search_as_you_type, edge n-gram, phrase_prefix, or a suitable prefix query.

### Forgetting to Query Shingle Sub-fields

Querying only the root field misses phrase signals provided by _2gram and _3gram. Use multi_match bool_prefix across the fields designed for search_as_you_type.

### Querying _index_prefix Directly in Every Case

_index_prefix is an internal sub-field serving prefix optimization for search_as_you_type. Normally, querying the root field and shingle sub-fields via bool_prefix is the intended usage.

### Using Edge N-gram in Both Index and Search Analyzers

Queries can be split into multiple prefixes, creating broad and hard-to-control semantics. Usually generate n-grams only at index time and use a standard normalizing search analyzer.

### Choosing min_gram Too Large

Users typing fewer characters than min_gram will find no results. Pick a value matching the desired UX.

### Choosing max_gram Too Small

Tokens longer than max_gram may lack a full term in the edge n-gram index. Raise the limit sensibly or pair with a regular full-text field.

### Using N-gram Instead of Edge N-gram Without Reason

N-grams emit substrings at multiple positions, bloating the index and matching unintended mid-word fragments. For word-start prefixes, edge n-gram is usually more appropriate.

### Assuming Edge N-gram Guarantees Phrase Order

Edge n-gram produces prefixes of individual tokens; it does not enforce that words appear adjacently in order. Use shingles, phrase queries, or search_as_you_type when order matters.

### Using Completion Suggester for General Full-Text Search

Completion fits curated suggestion lists. If you need to search documents across long content and multiple fields, search_as_you_type or full-text queries fit better.

### Forgetting to Reindex After Changing Analyzers

Already-indexed documents do not automatically receive new tokens. Reindex to apply the new analyzer to existing data.

### Not Limiting Results and Requests

Short prefixes can match a huge number of documents. Cap size, query length, concurrency, and debounce to protect the cluster.

## 25. Solution Selection Workflow

When designing a search box, decide using these steps:

1. Determine whether the data is free-form text, names from a list, or identifiers.
2. Determine whether the user wants to find a document or pick a curated suggestion.
3. For standard full-text search-as-you-type, try search_as_you_type.
4. If custom min/max prefixes and analyzers are needed, try edge n-gram with separate index/search analyzers.
5. If ordered phrases with only an incomplete final term are needed, evaluate match_phrase_prefix.
6. For prefixes on codes or keywords, use prefix queries on suitable keyword fields.
7. For suggestions from a fixed list, evaluate completion suggester.
8. Define analyzers, lowercasing, folding, diacritics, and language rules.
9. Design queries and boosts so the most relevant results rank at the top.
10. Test short prefixes, long prefixes, multi-part terms, and missing-data cases.
11. Measure index size, ingest speed, and query latency.
12. Plan for reindexing whenever mappings/analyzers change.

## Conclusion

Search-as-you-type enables finding documents while users are mid-way through typing words or phrases. Elasticsearch's search_as_you_type field type automatically creates a root field, shingle sub-fields, and an index-prefix sub-field; the common query pattern is multi_match with type bool_prefix across the root field and _2gram/_3gram fields. This approach suits common full-text needs and reduces custom analyzer work.

Edge n-gram gives control over min_gram, max_gram, and analyzers. Generate prefixes at index time, use a normal normalizing search analyzer at search time, and consider index size when choosing gram ranges. Edge n-gram does not automatically enforce phrase word order, so pairing with shingles or phrase queries may be necessary. For identifiers, prefix queries on keyword fields usually fit better; for dedicated suggestion lists, completion suggester is worth considering. Final choices should rest on required user semantics, actual mappings/analyzers, top-result quality, and benchmarks at projected data scale.
