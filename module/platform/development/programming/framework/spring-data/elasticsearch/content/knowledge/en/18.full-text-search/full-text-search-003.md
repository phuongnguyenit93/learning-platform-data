# Multi-Match and Searching Across Multiple Fields

In full-text search, users often do not know exactly which field contains the information they are looking for. A product might be found by name, brand, description, or category code; an article might be found by title, body, or author name. Querying only a single field can cause the application to miss documents where the matching information resides in another field.

Elasticsearch provides the **multi_match** query to search the same keywords across multiple fields in a single request. The application can specify the list of fields, assign different weights to each field, and choose how relevance scores are combined. Multi-match supports several execution types, so the chosen `type` directly affects how terms are distributed across fields and how documents are ranked.

In Spring Data Elasticsearch, multi-match can be constructed using NativeQuery and lambda expressions from the Elasticsearch Java API Client. This approach lets you combine multi-field search with bool, filter, pagination, sort, and other Query DSL components.

## 1. Why Search Across Multiple Fields?

Suppose a products index stores documents:

    {
      "name": "Mechanical Keyboard K8",
      "brand": "Keychron",
      "description": "Wireless mechanical keyboard with compact layout",
      "category": "accessories"
    }

Users might enter:

- mechanical keyboard: information appears in name and description.
- Keychron: information appears in brand.
- compact layout: information appears in description.
- K8: information appears in name.

If you only use match on name, a search for Keychron will not find the product. If the application runs a separate query for each field and merges results manually, the code becomes more complex and must handle deduplication, pagination, and ranking itself.

multi_match lets you declare multiple fields in one query:

    GET products/_search
    {
      "query": {
        "multi_match": {
          "query": "mechanical keyboard",
          "fields": [
            "name",
            "brand",
            "description"
          ]
        }
      }
    }

Elasticsearch builds corresponding queries for the specified fields and combines them according to the chosen type. The result is a single set of documents ranked according to multi-match semantics.

## 2. Basic Structure of multi_match

A multi-match query commonly includes these components:

| Component | Role |
|---|---|
| query | The text the user wants to search for |
| fields | List of fields participating in the search |
| type | How queries and scores across fields are combined |
| operator | How terms analyzed from the query are combined |
| minimum_should_match | Number or percentage of terms required to match in supported modes |
| tie_breaker | How extra score from fields other than the best field is added in certain types |
| fuzziness | Allows approximate matching for certain query types |
| analyzer | Analyzer used to analyze the query |
| boost | Field or query weight to adjust ranking |

Example:

    {
      "query": {
        "multi_match": {
          "query": "wireless keyboard",
          "fields": [
            "name^3",
            "brand^2",
            "description"
          ],
          "type": "best_fields",
          "operator": "and"
        }
      }
    }

In this example:

- name has boost 3, prioritizing matches in the name.
- brand has boost 2.
- description uses the default weight.
- best_fields evaluates based on the best-matching field, with optional additional score contribution via tie_breaker if configured.
- operator and requires the query terms to match according to the semantics of each generated field query.

Boost is not a probability percentage. It is a multiplier affecting score, and its real impact also depends on BM25, field length, term frequency, analyzers, and other clauses.

## 3. Declaring Fields and Field Boosts

The fields list determines where Elasticsearch searches. You can list fields explicitly or use controlled wildcards.

Example:

    "fields": [
      "title",
      "summary",
      "content"
    ]

If one field is more important, you can increase its boost using the field^weight syntax:

    "fields": [
      "title^4",
      "summary^2",
      "content"
    ]

Article search example:

    GET articles/_search
    {
      "query": {
        "multi_match": {
          "query": "spring elasticsearch",
          "fields": [
            "title^4",
            "tags^2",
            "body"
          ]
        }
      }
    }

A document matching the terms in title can rank higher than one matching only in body. Boost expresses the relative importance of fields according to product goals.

### Choosing fields intentionally

Do not include every field in multi-match just because you can. Fields like internal_note, raw_payload, debug_message, or metadata that do not serve user search can introduce noise and increase query cost.

Select fields based on:

- What users expect when entering keywords.
- Field mapping type and analyzer.
- Field importance in ranking.
- Data size and term frequency.
- Fields with duplicated content or multi-fields of each other.

Wildcard field expansion can be convenient, but if the mapping changes and a new field matches the wildcard, query behavior can change as well. An explicit field list is usually easier to control for critical business APIs.

## 4. Main multi_match Types

The type property controls how multi-match combines queries across multiple fields. Common types include:

| Type | General behavior | Use case |
|---|---|---|
| best_fields | Runs a query per field and prioritizes the best-matching field | One field usually contains most of the searched content |
| most_fields | Combines scores across multiple fields | Same content indexed in multiple forms or analyzers |
| cross_fields | Treats multiple fields as parts of one logical field, term by term | First/last names or complementary short fields |
| phrase | Searches for an ordered phrase in each field | Words must appear close together and in order |
| phrase_prefix | Searches for a phrase where the last term is treated as a prefix | Suggesting phrases as the user types |
| bool_prefix | Uses match_bool_prefix on each field and combines results | Search-as-you-type queries |

If type is omitted, multi_match defaults to best_fields. Choose the type based on data structure and desired behavior, not merely its name.

## 5. best_fields: Prioritizing the Best-Matching Field

best_fields is the default type. It runs a match query on each field and combines results similarly to dis_max. A document is scored primarily based on the single field with the highest score.

Example:

    {
      "query": {
        "multi_match": {
          "query": "wireless keyboard",
          "type": "best_fields",
          "fields": [
            "name^3",
            "description"
          ]
        }
      }
    }

This type works well when:

- A single field usually contains the full content the user is looking for.
- A strong match in name matters more than splitting words between name and description.
- You want the best field to largely determine result ordering.

### Operator and minimum_should_match in best_fields

With best_fields, multi-match builds a separate match query for each field. Therefore, operator and minimum_should_match apply inside each individual field query.

Suppose the query is:

    "Will Smith"

and fields are first_name, last_name with operator and. A document with first_name = Will and last_name = Smith may not match best_fields as the user expects, because each individual field query must match both terms. Neither field contains both words on its own.

This is a key difference between best_fields and cross_fields. When fields are complementary parts of a single name, cross_fields is usually more suitable.

### tie_breaker

best_fields can use tie_breaker to add a fraction of the score from other matching fields in addition to the highest-scoring field.

Example:

    {
      "query": {
        "multi_match": {
          "query": "wireless keyboard",
          "type": "best_fields",
          "tie_breaker": 0.2,
          "fields": [
            "name^3",
            "description"
          ]
        }
      }
    }

A tie_breaker of 0.2 allows scores from other matching fields to contribute partially to the final score. This value should be tested on real data; do not assume increasing tie_breaker always improves relevance.

## 6. most_fields: Combining Scores Across Multiple Fields

most_fields also creates a match query per field, but its goal is to sum scores from multiple matching fields. It is useful when the same content is indexed multiple times with different analysis.

For example, a title with a main field and multi-fields using different analyzers:

    PUT articles
    {
      "mappings": {
        "properties": {
          "title": {
            "type": "text",
            "analyzer": "standard",
            "fields": {
              "english": {
                "type": "text",
                "analyzer": "english"
              },
              "exact": {
                "type": "text",
                "analyzer": "standard"
              }
            }
          }
        }
      }
    }

The application can search across multiple representations:

    {
      "query": {
        "multi_match": {
          "query": "running shoes",
          "type": "most_fields",
          "fields": [
            "title",
            "title.english",
            "title.exact"
          ]
        }
      }
    }

Each field can contribute score according to its own analysis. This is useful when combining indexing strategies such as language analyzers, normalization analyzers, or another variant of the content.

Do not use most_fields simply because you want to search several ordinary fields. If fields hold independent pieces of information, best_fields or cross_fields may express the goal better.

## 7. cross_fields: Searching Terms Across Complementary Fields

cross_fields is an important choice when fields form a single logical piece of information. For example, a person's name stored separately:

    {
      "first_name": "Will",
      "last_name": "Smith"
    }

The user enters Will Smith. Both terms need to be found, yet each term sits in a different field. With best_fields and operator and, each individual field query requires both terms in the same field.

cross_fields operates in a term-centric manner: terms in the query can be searched across the specified fields as if they belonged to one logical field, provided the fields have compatible analyzers.

Example:

    {
      "query": {
        "multi_match": {
          "query": "Will Smith",
          "type": "cross_fields",
          "operator": "and",
          "fields": [
            "first_name",
            "last_name"
          ]
        }
      }
    }

In this case, the term Will can match in first_name and Smith can match in last_name. Both terms must appear across the field set.

### Analyzer limitations in cross_fields

cross_fields groups fields by analyzer. Fields with different analyzers may be processed as separate groups, so they are not always treated as a single unified field.

Therefore, when using cross_fields:

- Choose fields with identical or compatible analyzers.
- Check the search analyzer of each field.
- Avoid mixing fields with very different languages or normalization rules in the same group.
- Test behavior with multi-term queries and missing fields.

cross_fields typically fits short, complementary fields like first_name and last_name. It does not automatically solve every multi-field search problem.

## 8. phrase: Searching for a Phrase Across Multiple Fields

If users need to find a phrase in order, type phrase creates a match_phrase query on each field.

Example:

    {
      "query": {
        "multi_match": {
          "query": "distributed search engine",
          "type": "phrase",
          "fields": [
            "title^3",
            "description"
          ]
        }
      }
    }

With phrase, terms must appear in order and close together per match_phrase semantics. You can configure slop to allow a certain amount of gap or positional shift.

Example:

    {
      "query": {
        "multi_match": {
          "query": "distributed search",
          "type": "phrase",
          "slop": 2,
          "fields": [
            "title",
            "body"
          ]
        }
      }
    }

slop should be chosen based on phrase requirements. Larger values make the query more flexible but can also produce less precise results.

Phrase search is usually more expensive than regular match and is not the default choice for every full-text query.

## 9. phrase_prefix: Prefix at the End of a Phrase

phrase_prefix fits cases where the user is typing a phrase and the last term is incomplete.

Example query:

    "quick brown fo"

This can match a phrase with the matching start and a final word starting with fo. Query JSON:

    {
      "query": {
        "multi_match": {
          "query": "quick brown fo",
          "type": "phrase_prefix",
          "fields": [
            "title",
            "description"
          ],
          "max_expansions": 20
        }
      }
    }

max_expansions limits the number of expansions for the trailing prefix. Too large a value can make the query more resource-intensive.

phrase_prefix is not equivalent to edge n-grams. It performs phrase matching with a trailing prefix at query time, whereas edge n-grams generate prefixes at index time. Evaluate both against latency, accuracy, and index size requirements.

## 10. bool_prefix and search-as-you-type

bool_prefix runs match_bool_prefix on each field and combines the results. Terms before the last term are treated as normal terms, while the last term is used as a prefix.

Example:

    {
      "query": {
        "multi_match": {
          "query": "quick brown fo",
          "type": "bool_prefix",
          "fields": [
            "title",
            "title._2gram",
            "title._3gram"
          ]
        }
      }
    }

This type is commonly used with the search_as_you_type field type, which generates subfields dedicated to searching as the user types.

Example mapping:

    PUT articles
    {
      "mappings": {
        "properties": {
          "title": {
            "type": "search_as_you_type"
          }
        }
      }
    }

A common query:

    GET articles/_search
    {
      "query": {
        "multi_match": {
          "query": "quick brown fo",
          "type": "bool_prefix",
          "fields": [
            "title",
            "title._2gram",
            "title._3gram"
          ]
        }
      }
    }

The subfields are generated by Elasticsearch according to the search_as_you_type configuration. They support prefix matching and term ordering in different ways. If the problem is autocomplete, consider search_as_you_type before building a complex custom n-gram setup.

## 11. How Mapping and Analyzers Affect multi_match

multi_match does not bypass mappings. Each field is analyzed according to its corresponding analyzer. If a field is text, query text is split into tokens by the search analyzer. If a field is keyword, the value is typically kept intact as a single term.

Example mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "analyzer": "standard"
          },
          "brand": {
            "type": "text",
            "analyzer": "standard"
          },
          "category": {
            "type": "keyword"
          },
          "description": {
            "type": "text",
            "analyzer": "english"
          }
        }
      }
    }

If multi-match searches name, brand, category, and description at once, each field may analyze the query differently. This can produce inconsistent results, especially with cross_fields.

### Text and keyword

Text fields suit full-text search because content is analyzed into tokens. Keyword fields suit exact matching, filtering, sorting, and aggregations.

If you need to search category names as phrases, use a separate text field or multi-field instead of expecting match on a keyword field to tokenize words like text.

### Search analyzer

A field can declare a search_analyzer different from its index-time analyzer. Multi-match uses the appropriate search analyzer for each field when constructing the query.

When fields use different analyzers, especially with cross_fields, inspect analyzer groups and how the query is split. Do not assume that listing fields together means they are all processed as the same text.

### Inspecting analyzers with the Analyze API

You can see how Elasticsearch analyzes a string:

    POST products/_analyze
    {
      "field": "name",
      "text": "Mechanical Keyboards"
    }

Do the same for description or other fields to compare tokens. This helps explain why a term matches in one field but not another.

## 12. Using multi_match in Spring Data Elasticsearch

In modern Spring Data Elasticsearch, you can create a NativeQuery using the Spring Data builder and Elasticsearch Java API Client lambdas.

Example service searching products by name, brand, and description:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> search(
                String keyword,
                Pageable pageable) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .multiMatch(m -> m
                        .query(keyword)
                        .fields(
                            "name^3",
                            "brand^2",
                            "description"
                        )
                        .type(TextQueryType.BestFields)
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

Related imports:

    import co.elastic.clients.elasticsearch._types.query_dsl.TextQueryType;
    import org.springframework.data.domain.Pageable;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
    import org.springframework.data.elasticsearch.core.SearchHits;

In the example:

- ElasticsearchOperations is injected via the constructor.
- NativeQuery.builder() creates the Spring Data query.
- withQuery takes a lambda constructing the Elasticsearch Query.
- multiMatch creates a multi-match query.
- query(keyword) sets the search content.
- fields declares the fields and boosts.
- type(TextQueryType.BestFields) selects best_fields combination.
- withPageable applies pagination.
- operations.search executes and maps results to Product.

Enum names and builder signatures must match the Elasticsearch Java API Client version managed by Spring Data in the project. If your version lacks an overload or enum shown in the example, check the corresponding dependency and use the types provided by that version.

## 13. Combining multi_match with bool and filter

In real applications, multi-match is usually the primary search condition, while status, category, or date ranges are filter conditions.

Example:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .multiMatch(mm -> mm
                        .query(keyword)
                        .fields(
                            "name^3",
                            "brand^2",
                            "description"
                        )
                        .type(TextQueryType.BestFields)
                        .operator(Operator.And)
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of(category))
                    )
                )
            )
        )
        .withPageable(pageable)
        .build();

Additional imports:

    import co.elastic.clients.elasticsearch._types.FieldValue;
    import co.elastic.clients.elasticsearch._types.query_dsl.Operator;

Here:

- multi_match inside must specifies the searched content and contributes to the score.
- operator AND requires the query terms to match according to the chosen type's semantics.
- status and category filters restrict the result set without adding score.
- Pageable controls pagination.

With best_fields, operator applies inside each field query. If keywords can be scattered across complementary fields, consider cross_fields rather than just changing the operator.

## 14. cross_fields Example in Spring Data

Suppose entity Person has firstName and lastName. The user enters a full name:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query("Will Smith")
                .fields("firstName", "lastName")
                .type(TextQueryType.CrossFields)
                .operator(Operator.And)
            )
        )
        .build();

This query indicates that terms can match across fields in the same analyzer group. It fits complementary short fields as long as analyzers are compatible.

If firstName and lastName have different analyzers, results may not match expectations because cross_fields processes analyzer groups separately. Check mappings and analyzers before using it.

## 15. multi_match with phrase Example

If searching requires an ordered phrase across multiple fields:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query("distributed search engine")
                .fields("title^3", "body")
                .type(TextQueryType.Phrase)
                .slop(1)
            )
        )
        .build();

Phrase fits when term order and proximity matter. Slop provides a controlled degree of flexibility. Test results on real data because phrase queries are typically stricter than match queries and can miss documents users still expect to find.

Fuzziness is not supported for phrase and phrase_prefix types in standard multi_match usage. If fuzzy matching is needed, pick a compatible type and verify Query DSL limits.

## 16. Operator and minimum_should_match

A multi-word query is split by the analyzer into terms. Operator controls how those terms are combined:

- OR: only needs to match one or more terms per query semantics.
- AND: requires every term in the query to match.

Example:

    {
      "query": {
        "multi_match": {
          "query": "wireless mechanical keyboard",
          "fields": [
            "name",
            "description"
          ],
          "operator": "and"
        }
      }
    }

minimum_should_match lets you set a minimum count or percentage of terms that must match. Example:

    {
      "query": {
        "multi_match": {
          "query": "wireless mechanical keyboard",
          "fields": [
            "name",
            "description"
          ],
          "minimum_should_match": "2"
        }
      }
    }

With best_fields and most_fields, operator and minimum_should_match apply to each individual field query. Therefore, they do not automatically allow the first term to appear in name and the next in description.

With cross_fields, term-centric combination is better suited when words can be distributed across multiple fields. However, analyzer grouping still affects execution.

## 17. Fuzziness and Approximate Matching

Fuzziness allows a small number of character differences per term, helpful for minor user typos:

    {
      "query": {
        "multi_match": {
          "query": "keybord",
          "fields": [
            "name",
            "description"
          ],
          "fuzziness": "AUTO"
        }
      }
    }

Elasticsearch can find keyboard even if the user types keybord, depending on term length and fuzziness configuration.

Fuzzy queries increase search cost because Elasticsearch must expand terms into approximate variants. Do not enable fuzziness on every field and every query without measuring performance.

Some limitations:

- Fuzziness cannot be used with phrase and phrase_prefix types in multi_match.
- Very short prefixes or terms may not suit fuzzy matching.
- Fuzzy matching can produce unintended matches on product codes or identifiers.
- Consider fuzziness, prefix_length, and max_expansions based on requirements.

For product names or free-form content, fuzzy matching can improve user experience. For SKUs, emails, serial numbers, or statuses, more exact fields and queries are usually better.

## 18. Field Boost and Query Boost

There are two levels of boost to distinguish:

- Field boost in the fields list, such as title^4.
- Query boost on the entire query, if the builder/API supports configuring boost for multi-match.

Field boost expresses the relative importance of individual fields. Query boost changes the weight of the whole query relative to other clauses when combined in a bool query.

For example, a search with:

- multi_match on name and description.
- filter by category.
- should query on brand to boost score.

You can use field boost to prioritize name, and query boost or should to prioritize another signal. However, scoring combines many factors; boosts should be tuned with an evaluation query set rather than chosen by intuition.

## 19. multi_match and nested Fields

multi_match can search object-mapped nested fields using dotted names when appropriate. However, for the nested mapping type, simply putting the field name in the multi_match list does not automatically create a nested query.

Example mapping:

    {
      "properties": {
        "offers": {
          "type": "nested",
          "properties": {
            "seller": {
              "type": "text"
            },
            "description": {
              "type": "text"
            }
          }
        }
      }
    }

To search inside a nested object, wrap multi_match inside a nested query:

    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "multi_match": {
              "query": "trusted seller",
              "fields": [
                "offers.seller",
                "offers.description"
              ]
            }
          }
        }
      }
    }

A nested query preserves the relationship between fields within the same nested object. Querying nested fields directly like regular fields may be rejected by Elasticsearch or fail to yield intended results.

## 20. Pagination, Sorting, and SearchHits Results

Multi-match only handles the query and scoring part. A search API typically also needs pagination and may need sorting.

Example:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("_score"))
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query(keyword)
                .fields("title^3", "body")
                .type(TextQueryType.BestFields)
            )
        )
        .withPageable(pageable)
        .build();

    SearchHits<Article> hits =
        operations.search(query, Article.class);

Normally, full-text results are ordered by descending score unless another sort overrides it. If you sort by a field such as createdAt, results will be prioritized by that field instead of solely by relevance.

If you need to combine relevance and time, design an appropriate sort and verify API support for sorting by score alongside fields. For deep pagination, consider search_after and a stable sort order instead of increasing from too much.

SearchHits holds the score and metadata of each hit:

    for (SearchHit<Article> hit : hits) {
        Article article = hit.getContent();
        float score = hit.getScore();
    }

If the application needs to show why a result was prioritized, consider the Explain API or query profiling in an analysis environment. Do not run explain on every production request because its cost can be high.

## 21. Multi-match Compared to Alternatives

Not every multi-field search problem requires multi_match.

| Approach | When suitable | Considerations |
|---|---|---|
| Multi-match | Same query searched across multiple fields, choosing how to combine scores | Must understand types and analyzers |
| Bool with multiple match clauses | Each field has distinct conditions or weights | Longer query but explicit control |
| copy_to | Want to combine content of multiple fields into one composite search field | Requires mapping design and reindexing when changed |
| Combined fields query | Want term-centric search across multiple fields as one logical field with its own scoring | Must check compatible fields and analyzers |
| search_as_you_type | Autocomplete on phrase-like content | Increases index structure and needs appropriate queries |
| Completion suggester | Suggestions from a pre-prepared list | Does not replace general full-text search |

### Multi-match and copy_to

copy_to copies content from multiple fields into a single target field when indexing a document. The application can then query just that target field.

Example:

    {
      "properties": {
        "name": {
          "type": "text",
          "copy_to": "search_text"
        },
        "brand": {
          "type": "text",
          "copy_to": "search_text"
        },
        "description": {
          "type": "text",
          "copy_to": "search_text"
        },
        "search_text": {
          "type": "text"
        }
      }
    }

This is convenient when fields serve a combined search text. However, it loses per-field boost control at query time and requires explicit target field design.

### Multi-match and combined_fields

Elasticsearch offers the combined_fields query for term-centric search across multiple compatible fields. It can be a good fit when treating fields as a single logical field using combined fields scoring. Capabilities and limits depend on the Elasticsearch version.

multi_match cross_fields also serves term-centric search but has distinct semantics, including grouping fields by analyzer. When exact cross-field scoring control matters, compare multi_match cross_fields and combined_fields with a representative query set.

## 22. Testing Queries and Relevance

A multi-match query can be syntactically valid yet produce results that do not serve users well. Evaluate relevance with realistic queries.

A testing workflow:

1. Prepare a representative query set reflecting how users search.
2. For each query, record the expected documents.
3. Run the query with types such as best_fields, most_fields, or cross_fields.
4. Experiment with different boost levels for important fields.
5. Compare result ordering and relevant result counts.
6. Test cases with missing fields, synonyms, typos, and multiple analyzers.
7. Monitor latency and query cost as the number of fields grows.

Evaluation metrics can include precision@k, recall@k, mean reciprocal rank, or nDCG if relevance labels exist. For small apps, even a manually judged query set is better than trying a few random examples.

### Using the Explain API

When a document has an unexpected score, the Explain API shows what contributed to the score:

    GET products/_explain/p-101
    {
      "query": {
        "multi_match": {
          "query": "mechanical keyboard",
          "fields": [
            "name^3",
            "description"
          ],
          "type": "best_fields"
        }
      }
    }

Explain helps identify which field contributed points and which terms matched. Use it only during analysis because responses can be large and the operation is more expensive than a regular search.

## 23. Common Mistakes

### Using best_fields for complementary fields

If a phrase is split across first_name and last_name, best_fields with operator AND may fail to match because each individual field query must contain every term. Consider cross_fields.

### Thinking operator AND applies across the whole field list

With best_fields and most_fields, operator applies inside each individual field query. It does not automatically combine terms across multiple fields. cross_fields provides more term-centric semantics.

### Using cross_fields with incompatible analyzers

cross_fields groups fields by analyzer. If fields use different analyzers, they may not be combined as a single unified field. Check mappings and the Analyze API.

### Boosting fields too high

Excessive boosts can let one field dominate nearly the entire ranking order. Test on a query set with relevance judgments.

### Putting keyword fields into full-text queries without checking mapping

Keyword fields are not analyzed like text. If you need word-by-word search, use a text field or an appropriate multi-field.

### Using fuzziness for every query

Fuzzy matching has a cost and does not suit every type or data kind. Do not use it on identifiers when exact matches are required.

### Using phrase when only independent words are needed

Phrase queries require term order and proximity, potentially missing results that regular match would find. Use it only when phrase order is part of the requirement.

### Confusing phrase_prefix with edge n-gram

phrase_prefix expands the last term at query time. Edge n-gram generates prefixes at index time. They have different costs and behaviors.

### Ignoring nested mappings

Fields inside a nested object require a nested query. Multi-match does not automatically create a nested context just because a field name contains a dot.

### Using wildcard fields without control

Wildcards can unintentionally include new or unrelated fields after a mapping change. Restrict the field list or verify expansion results.

## 24. Process for Choosing a multi_match Type

Before writing the query, answer these questions:

1. Are the fields independent places that could each contain the entire query, or complementary parts?
2. Should the single best field largely determine the score?
3. Do multiple fields contain the same content indexed with different analyzers?
4. Do users need independent words or an ordered phrase?
5. Are users typing part of a phrase or do they need fuzzy matching?
6. Do the fields share compatible analyzers and mappings?
7. Which fields matter more and need boosting?

Selection guidelines:

- Choose best_fields when one field usually contains most of the matching content.
- Choose most_fields when the same content is indexed in multiple forms and you want to combine scores.
- Choose cross_fields when terms can reside in complementary fields like first_name and last_name.
- Choose phrase when phrase order matters.
- Choose phrase_prefix or bool_prefix when searching phrases as the user types.

After picking the type, review operator, minimum_should_match, tie_breaker, boost, and analyzer. These parameters can significantly alter results even when the field list stays the same.

## Conclusion

multi_match allows searching the same query across multiple fields and combining results according to a specific type. best_fields prioritizes the best-matching field; most_fields combines scores across multiple representations; cross_fields suits complementary fields term by term; phrase, phrase_prefix, and bool_prefix serve phrase search and search-as-you-type needs.

In Spring Data Elasticsearch, NativeQuery.builder() paired with the multiMatch lambda is a natural way to build multi-field queries. Choose fields based on mappings and user needs, apply boosts intentionally, understand operator/minimum_should_match per type, and verify analyzer compatibility. Finally, evaluate relevance with representative queries and monitor latency rather than assuming a syntactically valid query already produces good results.
