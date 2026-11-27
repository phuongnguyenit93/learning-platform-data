# Completion Suggester and Suggestion Input Data

Completion suggester is a mechanism for suggesting word or phrase completions as the user types. For example, when the user types "mech", the application can suggest "Mechanical Keyboard", "Mechanical Switch", or other matching product names before they submit the full query.

Spring Data Elasticsearch supports completion fields via the `@CompletionField` annotation, the `Completion` class to describe input data, and `NativeQuery` to send the suggester in a search request. Results are returned in the suggest metadata of `SearchHits`, separate from the regular list of document hits.

To implement this feature well, suggestion data must be designed starting at index time. A completion field can hold multiple inputs, weights, and contexts. This data determines what gets suggested, how suggestions are ranked, and what scope users see.

## 1. What Problem Does Completion Suggester Solve?

Completion suggester powers autocomplete or search-as-you-type. Users type part of a phrase and the system returns complete phrases starting with what was entered.

| Typed Input | Suggestions That May Be Returned |
| --- | --- |
| mech | Mechanical Keyboard, Mechanical Switch |
| key | Keyboard, Keycap Set, Keychron K8 |
| iph | iPhone 17, iPhone 17 Pro |
| wire | Wireless Mouse, Wireless Headset |

Completion suggester is optimized for low latency. Elasticsearch builds a dedicated lookup structure from completion data at index time and keeps that structure in memory. This makes prefix lookups fast, in exchange for noticeable index build cost and heap consumption.

Completion suggester fits navigation suggestions pointing to known values such as product names, brands, locations, categories, or article titles.

### 1.1. Distinguishing Completion, Term, and Phrase Suggesters

Elasticsearch has several suggester types serving different goals:

| Type | Goal | Example |
| --- | --- | --- |
| Completion suggester | Complete prefixes while the user types | key → Keyboard |
| Term suggester | Suggest similar words to fix spelling errors | keybord → keyboard |
| Phrase suggester | Suggest rewriting entire phrases based on word context | noble prize → nobel prize |

Completion suggester is not a general-purpose spell checker. It focuses on prefixes and can enable fuzziness to tolerate a few typing mistakes.

If you need mid-word substring matching, content-based search, or multi-condition querying, consider search_as_you_type, edge n-gram, match query, or regular search queries. Completion suggester is primarily a pre-prepared list of suggestions.

## 2. Completion Field Mapping

Elasticsearch requires the field used for completion suggester to have mapping type completion. You cannot take an ordinary text field and send a completion query against it.

Minimal JSON mapping:

~~~json
{
  "mappings": {
    "properties": {
      "suggest": {
        "type": "completion"
      }
    }
  }
}
~~~

Spring Data Elasticsearch provides the `@CompletionField` annotation to declare the mapping:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions")
public class ProductSuggestionDocument {

    @Id
    private String id;

    @CompletionField
    private Completion suggest;

    // Other business fields, constructors, getters and setters
}
~~~

`@CompletionField` causes the suggest field to be created with type completion in the mapping. Spring Data's `Completion` class represents the input values, weight, and contexts sent to Elasticsearch.

### 2.1. Attributes of CompletionField

`@CompletionField` supports important attributes:

| Attribute | Meaning | Default Value |
| --- | --- | --- |
| analyzer | Analyzer used when indexing inputs | simple |
| searchAnalyzer | Analyzer used when analyzing query prefixes | simple |
| preserveSeparators | Preserves separators between tokens | true |
| preservePositionIncrements | Preserves token position increments, useful with stop words | true |
| maxInputLength | Limits length of each input when indexing | 50 |
| contexts | Declares category or geo contexts | None |

Explicit configuration example:

~~~java
@CompletionField(
    analyzer = "simple",
    searchAnalyzer = "simple",
    preserveSeparators = true,
    preservePositionIncrements = true,
    maxInputLength = 80
)
private Completion suggest;
~~~

`maxInputLength` caps each input string at index time to avoid an overly long input bloating the completion structure. The default is 50 UTF-16 code points. If the application suggests long product names or places, set the limit based on real data.

### 2.2. preserveSeparators

When `preserveSeparators` is true, separators between words are preserved when analyzing inputs. This affects how prefixes match multi-word phrases.

Example input Foo Fighters:

- With separators preserved, the prefix must follow the indexed word structure.
- If separators are disabled, a prefix like foof can match Foo Fighters.

Do not disable this attribute just to solve one edge case. You can index an alternative input such as FooFighters or a normalized alias if you want to support another typing pattern.

### 2.3. preservePositionIncrements

This attribute relates to token position gaps when an analyzer removes stop words. If disabled, certain prefixes can match words after a stop word.

For example, the band name The Beatles: the application may want prefix b to suggest The Beatles. You can configure a suitable analyzer and position increments, or add Beatles as an alias input. Adding explicit inputs is usually easier to control if the dataset is not overly large.

## 3. Completion Input, Weight, and Contexts

A completion value typically has three parts:

~~~json
{
  "input": ["Mechanical Keyboard", "Keyboard", "KB-1042"],
  "weight": 120,
  "contexts": {
    "category": ["keyboards", "accessories"]
  }
}
~~~

| Component | Role |
| --- | --- |
| input | Strings whose prefixes users may type to find the suggestion |
| weight | Weight used to rank suggestions |
| contexts | Context labels to filter or boost suggestions |

input is required. It can be a string or an array of strings. weight is an optional positive integer; larger values can help a suggestion rank higher. contexts is required only when the field declares context mappings.

Elasticsearch also supports multiple completion entries per document, each with its own input and weight. Spring Data's Completion class represents one group of inputs sharing a weight and contexts. If individual aliases need different weights, split them into separate suggestion documents or use the lower-level client API to send the appropriate entry structure.

### 3.1. Using Completion in an Entity

Spring Data's Completion class has constructors accepting an array or list of inputs. Weight and contexts are assigned via setters:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.data.elasticsearch.core.suggest.Completion;

Completion completion = new Completion(List.of(
    "Mechanical Keyboard",
    "Keyboard",
    "KB-1042"
));

completion.setWeight(120);
completion.setContexts(Map.of(
    "category", List.of("keyboards", "accessories")
));
~~~

When the field does not declare contexts, setContexts can be omitted. If the field declares a context mapping, each completion value must include corresponding contexts at index time, unless the mapping uses path to pull context from another field in the document.

### 3.2. Complete Entity Example

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions")
public class ProductSuggestionDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String displayName;

    @CompletionField(maxInputLength = 80)
    private Completion suggest;

    public void prepareSuggestion() {
        Completion value = new Completion(List.of(
            displayName,
            sku
        ));
        value.setWeight(100);
        this.suggest = value;
    }

    // Constructors, getters and setters
}
~~~

The prepareSuggestion method illustrates building completion inputs from business data. In real applications, place normalization and alias generation in a dedicated service or mapper so the entity does not hold too many business rules.

If a context mapping declares category, assign the context or configure a suitable path before saving.

## 4. Designing Suggestion Input Data

Autocomplete quality depends more on the indexed data than on the number of query options. A product document may have a display name, normalized name, SKU, brand, and aliases. Not every field should become an input.

| Source Data | Should It Become an Input? | Reason |
| --- | --- | --- |
| Product name | Yes | Usually what users want to select |
| Common short name | Yes | Supports familiar phrasing |
| SKU or product code | Yes if users frequently look up codes | Useful for identifier lookups |
| Brand name | Depends on UX | Can create dedicated brand suggestions |
| Long description | Usually no | Easily produces too many noisy inputs |
| HTML content | No | Not a valid suggestion string |
| Internal keywords | Only if valuable to users | Avoids leaking internal data |

### 4.1. Normalizing Inputs

A suggestion data preparation pipeline may include:

1. Extract display names and publicly permitted aliases.
2. Remove empty or whitespace-only strings.
3. Normalize whitespace and control characters.
4. Deduplicate inputs after normalization.
5. Enforce input length limits per mapping.
6. Assign weight based on business priority.
7. Attach category or geo contexts if the field has context mappings.
8. Write completion values with the document or into a dedicated suggestion index.

Elasticsearch rejects certain UTF-16 control characters in inputs, including null and information separator characters U+001F, U+001E. Clean data in the application layer before indexing.

### 4.2. Indexing Multiple Aliases for One Document

Example of a product with multiple names:

~~~json
{
  "sku": "KB-1042",
  "displayName": "Mechanical Keyboard",
  "suggest": {
    "input": [
      "Mechanical Keyboard",
      "Keyboard",
      "Mechanical Keyboards",
      "KB-1042"
    ],
    "weight": 120
  }
}
~~~

Users can find the same product through multiple inputs. Completion options can point back to the same document ID. If multiple documents share identical inputs, results may contain duplicate text suggestions; use skip_duplicates or design index inputs to minimize duplicates.

### 4.3. Choosing Weights by Business Rules

Weight is a positive integer used to increase/decrease suggestion priority. Weight can be derived from:

- Product or phrase popularity.
- Number of suggestion selections over a time window.
- Editorial priority status.
- Relevance by data category.
- Data quality and active sale status.

Illustrative example:

| Input Group | Suggested Weight |
| --- | ---: |
| Featured product name | 200 |
| Regular product name | 100 |
| Rarely used alias | 30 |

These numbers are only examples. Normalize weights so one data group does not dominate every suggestion. Log scaling or upper caps can be used if weights are computed from very large selection counts.

Weight does not completely override prefix relevance. Completion suggester also considers matching prefix length; suggestions sharing a longer prefix may rank higher.

## 5. Indexing Suggestion Data via Spring Data

After creating an entity with a completion field, save it with ElasticsearchOperations:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

public class ProductSuggestionIndexer {

    private final ElasticsearchOperations operations;

    public ProductSuggestionIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void index(ProductSuggestionDocument document) {
        document.prepareSuggestion();
        operations.save(document);
    }
}
~~~

If the index does not exist yet, create the index with a mapping containing the completion field before writing data:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductSuggestionDocument.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

createWithMapping() uses entity metadata to build the mapping. If the application manages indices via migrations or index templates, verify that the actual mapping of the suggest field is completion before writing.

### 5.1. Near-Real-Time Completion

New suggestions appear after Elasticsearch refreshes the shard. This means:

- A newly indexed document may not appear in autocomplete immediately.
- After refresh, the new completion entry becomes queryable.
- Once a document is deleted and the change is refreshed, its suggestion is no longer returned.

Do not enable immediate refresh after every write in high-traffic applications. Use a refresh policy suited to your import or data sync pipeline.

### 5.2. Updating and Deleting Suggestions

Completion inputs are tied to the indexed document. When display names, aliases, statuses, or weights change, update the corresponding completion value.

For example:

- Product renamed: replace old inputs with the new name and valid aliases.
- Product discontinued: delete the suggestion document or remove stale inputs.
- Category changed: update the category context.
- Location coordinates changed: update the geo context.
- Popularity weight changed: recalculate weight and reindex.

If autocomplete has its own lifecycle separate from business data, use a dedicated suggestion index so updates, deletions, and access control can be managed independently.

## 6. Completion Suggester Using Query DSL

Completion suggester is declared in the suggest section of a search request. Each suggester has a custom name, a prefix to complete, and completion field configuration.

~~~http
POST product-suggestions/_search
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "mech",
      "completion": {
        "field": "suggest",
        "size": 10
      }
    }
  }
}
~~~

Meaning:

- product-autocomplete is the suggester name, used to extract the matching result group in the response.
- prefix is the text the user has entered.
- completion.field is the field mapped with type completion.
- size is the maximum number of suggestions returned.

If size is omitted, completion suggester returns at most 5 suggestions by default.

### 6.1. Removing Duplicate Suggestions

An input can appear across multiple documents. If the UI only wants each suggestion string to appear once, enable skip_duplicates:

~~~json
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "key",
      "completion": {
        "field": "suggest",
        "size": 10,
        "skip_duplicates": true
      }
    }
  }
}
~~~

skip_duplicates filters out suggestions with duplicate text. This property can slow queries because Elasticsearch must traverse extra candidates to find enough unique suggestions.

If multiple products share the same name, decide clearly whether the UI wants to:

- Show one name string and pick the best-matching document.
- Show multiple results with the same name plus distinguishing metadata.
- Suggest by name and transition to a full search query upon selection.

Do not enable skip_duplicates in every case blindly.

## 7. Using NativeQuery in Spring Data Elasticsearch

In modern Spring Data Elasticsearch, NativeQuery accepts a Suggester from the Elasticsearch Java API Client. This is how completion suggesters integrate into the ElasticsearchOperations.search(...) flow.

~~~java
import co.elastic.clients.elasticsearch.core.search.Suggester;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Suggester suggester = Suggester.of(s -> s
    .suggesters("product-autocomplete", field -> field
        .prefix("mech")
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

SearchHits<ProductSuggestionDocument> results =
    operations.search(query, ProductSuggestionDocument.class);
~~~

Here:

- Suggester is of type co.elastic.clients.elasticsearch.core.search.Suggester.
- NativeQuery.withSuggester(...) attaches the suggest section to the search request.
- ElasticsearchOperations.search(...) executes the request and maps the response to Spring Data abstractions.

Builder types belong to the Elasticsearch Java API Client. Use the client version managed by Spring Boot/Spring Data dependency management, avoiding mixing legacy High Level REST Client classes with the modern Java API Client.

### 7.1. Enabling Fuzzy Completion

Completion suggester supports fuzziness so users still get suggestions when mistyping a few characters:

~~~json
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "keybord",
      "completion": {
        "field": "suggest",
        "size": 10,
        "fuzzy": {
          "fuzziness": "AUTO",
          "min_length": 3,
          "prefix_length": 1,
          "transpositions": true
        }
      }
    }
  }
}
~~~

| Property | Meaning |
| --- | --- |
| fuzziness | Accepted edit distance; usually defaults to AUTO |
| min_length | Minimum prefix length before fuzzy matching activates |
| prefix_length | Number of leading characters that must match exactly |
| transpositions | Whether swapping two adjacent characters counts as a single edit |
| unicode_aware | Measure distance by Unicode code points instead of bytes |

Fuzziness tolerates typos but increases the number of candidates checked. Do not enable it for very short prefixes because it can yield many irrelevant suggestions. Test on real queries and measure latency.

### 7.2. Regex Completion

Completion suggester also supports regex to express complex prefixes:

~~~json
{
  "suggest": {
    "product-autocomplete": {
      "regex": "mech.*",
      "completion": {
        "field": "suggest",
        "size": 10
      }
    }
  }
}
~~~

Regex can consume significant CPU and memory if the expression generates a large automaton. Do not accept arbitrary regexes from users and forward them straight to the cluster. If the UI only needs standard autocomplete, prefix queries are simpler and easier to bound.

## 8. Reading the Completion Suggestion Response

Completion suggester returns a separate suggest section in the search response. The normal hits section may be empty while suggestion options still contain data.

~~~json
{
  "hits": {
    "total": {
      "value": 0,
      "relation": "eq"
    },
    "hits": []
  },
  "suggest": {
    "product-autocomplete": [
      {
        "text": "mech",
        "offset": 0,
        "length": 4,
        "options": [
          {
            "text": "Mechanical Keyboard",
            "_index": "product-suggestions",
            "_id": "KB-1042",
            "_score": 120,
            "_source": {
              "sku": "KB-1042",
              "displayName": "Mechanical Keyboard"
            }
          }
        ]
      }
    ]
  }
}
~~~

| Field | Meaning |
| --- | --- |
| text | Prefix or text segment used to build the suggestion entry |
| offset, length | Position and length of the input segment in the suggest text |
| options[].text | Returned suggestion string |
| options[]._id | Source document ID of the suggestion |
| options[]._index | Index holding the source document |
| options[]._score | Score of the completion option, influenced by weight and context boost |
| options[]._source | Source document content if source is enabled |

Do not assume SearchHits.getTotalHits() equals the number of completion options. Suggestions reside in SearchHits.getSuggest(), whereas getSearchHits() holds document hits from the regular query.

### 8.1. Retrieving Suggest from SearchHits

Spring Data provides SearchHits.getSuggest():

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.Suggest;

SearchHits<ProductSuggestionDocument> results =
    operations.search(query, ProductSuggestionDocument.class);

Suggest suggest = results.getSuggest();

if (suggest != null) {
    var productSuggestion =
        suggest.getSuggestion("product-autocomplete");
}
~~~

Suggest.getSuggestion(name) returns a generic suggestion type. For completion suggester, cast to CompletionSuggestion<T> after confirming the type:

~~~java
import org.springframework.data.elasticsearch.core.suggest.response.CompletionSuggestion;

if (productSuggestion instanceof CompletionSuggestion<?> completionSuggestion) {
    for (CompletionSuggestion.Entry<?> entry : completionSuggestion.getEntries()) {
        for (CompletionSuggestion.Entry.Option<?> option : entry.getOptions()) {
            String text = option.getText();
            Double score = option.getScore();
        }
    }
}
~~~

Each entry has a list of options. option.getText() is the suggested string; option.getScore() is the score returned for the option.

### 8.2. Getting the Suggestion's Source Document

A completion option can hold a SearchHit<T> representing the source document:

~~~java
for (CompletionSuggestion.Entry<?> entry : completionSuggestion.getEntries()) {
    for (CompletionSuggestion.Entry.Option<?> option : entry.getOptions()) {
        String suggestedText = option.getText();

        var sourceHit = option.getSearchHit();
        if (sourceHit != null) {
            Object source = sourceHit.getContent();
            String documentId = sourceHit.getId();
        }
    }
}
~~~

The exact content type depends on the generic type used when calling operations.search(...) and how Spring Data maps source. You can read getSearchHit() to obtain the entity and source ID if the response contains source.

source is enabled by default in Elasticsearch. If source is disabled or the response omits source, the option can still provide text/ID without the full entity content.

### 8.3. Reducing Source Size

Completion responses can return the entire document _source for every option. If documents are large, fetching and transmitting source can increase cost.

When using _search, you can restrict source:

~~~json
{
  "_source": ["sku", "displayName"],
  "suggest": {
    "product-autocomplete": {
      "prefix": "mech",
      "completion": {
        "field": "suggest",
        "size": 5
      }
    }
  }
}
~~~

Fetch only the fields the UI needs to display. The dedicated _suggest endpoint does not support source filtering the same way _search does; use suggest inside a search request when controlling _source is needed.

## 9. Context Suggester: Filtering and Boosting by Context

By default, Completion suggester considers every document in the index. If the application needs suggestions scoped by category, venue type, tenant, or geographic location, declare context mappings.

Elasticsearch supports two context types:

- category: attaches one or more category labels to a suggestion.
- geo: attaches one or more geographic locations to a suggestion.

Each context mapping has a distinct name. A completion field can declare up to 10 context mappings.

When a field has context mappings, suitable contexts must be provided at both index time and query time. Otherwise, the request may be rejected or fail to produce expected suggestions.

### 9.1. Category Context

JSON mapping:

~~~json
{
  "properties": {
    "category": {
      "type": "keyword"
    },
    "suggest": {
      "type": "completion",
      "contexts": [
        {
          "name": "category",
          "type": "category",
          "path": "category"
        }
      ]
    }
  }
}
~~~

path points to another field in the document used as the context. When indexing a document, Elasticsearch reads the category value from that field.

Spring Data annotation:

~~~java
import org.springframework.data.elasticsearch.annotations.CompletionContext;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "place-suggestions")
public class PlaceSuggestionDocument {

    @Field(type = FieldType.Keyword)
    private String category;

    @CompletionField(
        contexts = {
            @CompletionContext(
                name = "category",
                type = CompletionContext.ContextMappingType.CATEGORY,
                path = "category"
            )
        }
    )
    private Completion suggest;

    // Constructors, getters and setters
}
~~~

If path is not declared, the application must assign contexts directly on Completion:

~~~java
Completion completion = new Completion(List.of(
    "Coffee Shop",
    "Cafe"
));

completion.setContexts(Map.of(
    "category", List.of("cafe", "food")
));
~~~

### 9.2. Querying by Category

~~~json
{
  "suggest": {
    "place-suggestion": {
      "prefix": "cof",
      "completion": {
        "field": "suggest",
        "size": 10,
        "contexts": {
          "category": ["cafe", "restaurants"]
        }
      }
    }
  }
}
~~~

Multiple categories in the same context are combined with OR: a suggestion matches if it has at least one of the provided categories.

### 9.3. Boosting by Category

Contexts can both filter and boost scores:

~~~json
{
  "suggest": {
    "place-suggestion": {
      "prefix": "cof",
      "completion": {
        "field": "suggest",
        "size": 10,
        "contexts": {
          "category": [
            { "context": "cafe" },
            { "context": "restaurants", "boost": 2 }
          ]
        }
      }
    }
  }
}
~~~

In this example, suggestions belonging to restaurants get multiplied by a boost of 2. The final score is influenced by weight and context boost. If a suggestion matches multiple contexts, Elasticsearch uses the highest score among matching contexts.

### 9.4. Geo Context

Geo context lets you attach one or more geographic locations to suggestions and filter/boost by the user's region of interest.

JSON mapping:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    },
    "suggest": {
      "type": "completion",
      "contexts": [
        {
          "name": "location",
          "type": "geo",
          "path": "location",
          "precision": "5km"
        }
      ]
    }
  }
}
~~~

Querying by coordinates:

~~~json
{
  "suggest": {
    "place-suggestion": {
      "prefix": "cof",
      "completion": {
        "field": "suggest",
        "size": 10,
        "contexts": {
          "location": {
            "lat": 10.7769,
            "lon": 106.7009
          }
        }
      }
    }
  }
}
~~~

Geo context is encoded via geohashes at the configured precision. This is geohash region filtering, not an exact distance calculation like a geo_distance query. A place very close to the query coordinates that falls outside the encoded tile may not match. Choose precision and neighbors based on real-world geographic experience.

## 10. Analyzers and How Prefixes Are Analyzed

A completion field has an index analyzer and a search analyzer. Both analyzers must be designed consistently so inputs are indexed and prefixes are queried under the same tokenization rules.

The default analyzer for a completion field is simple. It lowercases letters and splits tokens on non-letter characters. If data contains SKUs, Vietnamese diacritics, special characters, or language-specific rules, test the analyzer on real data.

With Vietnamese, users may type with or without diacritics. The default analyzer does not automatically guarantee all typing variants are treated equivalently.

Options include:

- Using a custom analyzer with lowercase and asciifolding if normalizing diacritics is desired.
- Indexing additional accent-free aliases when explicit control is needed.
- Normalizing both input and query using the same rule in the application.

Do not change only the query-side analyzer without checking how completion inputs were indexed. If changing a completion analyzer or mapping, you typically must recreate the index and reindex data so the completion structure is rebuilt with the new analyzer.

### 10.1. Token Splitting and Separators

For multi-word phrases, preserveSeparators and preservePositionIncrements affect how prefixes match. Create a test suite covering:

- Prefixes from the first character of the phrase.
- Prefixes starting from the second word.
- Strings with hyphens.
- Strings with consecutive spaces.
- Names containing stop words.
- Names with diacritics and accent-free aliases.

If you want to support prefixes starting mid-phrase or from any token, consider indexing additional separate inputs instead of changing separator behavior across the entire dataset.

## 11. Completion Suggester Does Not Replace Search Queries

Autocomplete is usually a navigation step:

1. User types part of a keyword.
2. Completion suggester returns a list of suggestions.
3. User picks a suggestion.
4. Application uses the selected ID or text to open the document or run a full search query.

Completion suggester does not always return enough information to display complete search results. It may return options with filtered source. If the user hits Enter without selecting a suggestion, the application should still run a regular search query.

~~~text
User enters "mech"
          |
          v
Completion suggester
          |
          v
Mechanical Keyboard
Mechanical Switch
          |
          v
User selects Mechanical Keyboard
          |
          v
Open product by document ID
or run full search query
~~~

If you need to list documents filtered by multiple conditions such as price, stock, permissions, or relevance, use regular queries. Context suggester only fits contexts already indexed into the completion field.

## 12. Extracting Results and Building a DTO for the UI

Do not return internal Spring Data or Elasticsearch client structures directly from an API. Convert suggestion options into a small DTO:

~~~java
public record SuggestionItem(
    String text,
    String documentId,
    Double score
) {}
~~~

Illustrative mapper:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.suggest.response.CompletionSuggestion;

public List<SuggestionItem> toSuggestionItems(
        CompletionSuggestion<?> completionSuggestion) {

    List<SuggestionItem> items = new ArrayList<>();

    for (CompletionSuggestion.Entry<?> entry
            : completionSuggestion.getEntries()) {
        for (CompletionSuggestion.Entry.Option<?> option
                : entry.getOptions()) {

            SearchHit<?> hit = option.getSearchHit();
            String id = hit != null ? hit.getId() : null;

            items.add(new SuggestionItem(
                option.getText(),
                id,
                option.getScore()
            ));
        }
    }

    return items;
}
~~~

If product data is needed for display, read content from option.getSearchHit() when source is present. If source is not returned, use only text and ID and load details via another query.

## 13. Performance and Index Design

Completion suggester is optimized for lookup speed but carries a memory cost. Completion structures are kept in the JVM heap, so total input count, string lengths, context mappings, and shard count affect footprint.

A few guidelines:

- Only index inputs helpful for the autocomplete experience.
- Do not put entire long descriptions into a completion field.
- Cap maxInputLength.
- Deduplicate inputs before indexing.
- Keep weights within a sensible range.
- Only add context mappings when filtering or boosting is truly needed.
- Monitor completion field statistics and heap usage.
- Measure latency with production-like input volumes.

Elasticsearch recommends indexing completion data on a single shard for better latency in many cases, because multi-shard requests require an extra fetch phase for related documents. However, if one shard grows too large and pressures heap, split the index rather than forcing a single shard solely for completion.

### 13.1. Separating the Suggestion Index

A practical architecture:

| Index | Contents |
| --- | --- |
| products | Full product documents for querying and filtering |
| product-suggestions | Inputs, weights, category contexts, and minimal data for autocomplete |

Benefits:

- The completion index is smaller and contains only necessary data.
- Shard counts and refresh policies can be tuned independently.
- Easy to exclude products no longer allowed in suggestions.
- Separate read permissions can be applied to the suggestion index.

In return, the application must keep business documents and suggestion documents in sync. Use events, outbox patterns, or retryable sync jobs to prevent suggestions from pointing to deleted documents.

### 13.2. Refresh and Write Load

Frequent completion writes can increase refresh cost and lookup-structure rebuilds. When ingesting data in batches, consider bulk indexing and refreshing after the batch instead of per document.

For autocomplete where a few seconds of update delay is acceptable, near-real-time refresh is usually fine. If suggestions must appear immediately after a write, carefully evaluate the cost of the refresh policy.

## 14. Security and Suggestion Data Quality

Autocomplete can inadvertently leak data if indexed inputs contain internal names, unpublished documents, or values the user is not allowed to view.

A few guidelines:

- Only index data permitted for the current user audience.
- Never place secrets, tokens, private emails, or sensitive information into inputs.
- Use contexts or separate indices for tenant isolation when security requirements allow.
- Do not treat category context as a complete authorization mechanism if users can submit arbitrary queries.
- Validate prefix length and cap result counts.
- Do not accept arbitrary regexes from clients.
- Limit fuzziness to avoid high cost on overly short prefixes.
- Control which source fields are returned inside suggestion options.

If suggestion data depends on user permissions, authenticate and enforce access conditions in the application layer. A context filter only acts inside the suggester query; it does not replace API authorization.

## 15. Testing Completion Suggester

Verify mapping, indexed data, and query results.

### 15.1. Checking the Mapping

~~~http
GET /product-suggestions/_mapping
~~~

Confirm:

- The suggest field has type completion.
- Analyzer and search analyzer match the design.
- max_input_length is appropriate.
- Context mappings are declared accurately if used.
- Context paths point to existing fields with suitable data types.

### 15.2. Checking the Data

~~~http
GET /product-suggestions/_doc/KB-1042
~~~

Verify completion input, weight, and contexts are stored properly. If using path, verify the context's source field also holds values.

### 15.3. Checking Queries

~~~http
POST product-suggestions/_search
{
  "suggest": {
    "product-autocomplete": {
      "prefix": "mech",
      "completion": {
        "field": "suggest",
        "size": 10,
        "skip_duplicates": true
      }
    }
  }
}
~~~

Test these scenarios:

1. Prefix matching the exact start of an input.
2. Prefix with no results.
3. Prefix with mixed casing.
4. Prefix containing diacritics or special characters.
5. Multi-word prefix.
6. Prefix with typos when fuzziness is enabled.
7. Multiple documents sharing the same input.
8. Context filtering out the right group.
9. Newly updated documents after refresh.
10. Deleted documents no longer appearing after refresh.

### 15.4. Evaluating Suggestion Quality

Do not measure only latency. Evaluate:

- Correct suggestion rate in top 5 or top 10.
- Irrelevant suggestion rate.
- User suggestion click-through rate.
- Number of duplicate suggestions.
- Coverage of aliases and identifiers.
- Impact of weights and context boosts.

Logging prefixes and user selections under an appropriate data policy can help refine inputs and weights over time.

## 16. Common Pitfalls

**Using a text field instead of completion.** Completion queries require mapping type completion. Verify the mapping before querying.

**Declaring @CompletionField without recreating an existing index.** Annotations do not automatically alter existing index mappings. Create a new index or run a proper migration and reindex data.

**Not assigning inputs.** A completion value needs at least one valid input. Check the mapper creating the data before calling save.

**Indexing overly long inputs.** maxInputLength may truncate inputs at index time. Set an appropriate limit and inspect long names.

**Using completion for general spell checking.** Completion focuses on prefixes. Use term or phrase suggesters for dedicated spell correction.

**Expecting prefixes to match mid-word.** Completion is not substring search. Index suitable aliases or use search_as_you_type/edge n-gram for infix scenarios.

**Enabling fuzziness for overly short prefixes.** Can generate many noisy candidates and increase latency. Set appropriate min_length and prefix_length.

**Enabling skip_duplicates without measuring performance.** Elasticsearch must traverse extra candidates to find enough unique suggestions. Only enable when UX requires deduplication.

**Using zero or negative weights.** Weight must be a positive integer. Validate data before indexing.

**Declaring a context mapping without sending contexts.** Fields with contexts require contexts at both index time and query time. Verify path or assign contexts on Completion.

**Confusing geo context with exact distance.** Geo context uses geohash tiles. Use a geo_distance query if business rules require exact distance filtering.

**Reading SearchHits.getSearchHits() to retrieve completion options.** Completion options reside in SearchHits.getSuggest(). Regular hits may be empty.

**Not limiting suggestion source.** Large sources increase fetch and network costs. Return only the fields needed for display.

**Not syncing the suggestion index when business documents change.** Stale suggestions or deleted IDs can appear. Use events/outbox or retryable sync jobs.

## 17. Complete Example: Product Autocomplete

Suppose an application needs product suggestions by name and SKU. Inputs are prepared from display name, short name, and SKU; popular products carry higher weights.

Entity:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.CompletionField;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.suggest.Completion;

@Document(indexName = "product-suggestions")
public class ProductSuggestionDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String displayName;

    @Field(type = FieldType.Keyword)
    private String category;

    @CompletionField(maxInputLength = 80)
    private Completion suggest;

    public void buildSuggestion(int popularityWeight) {
        Completion completion = new Completion(List.of(
            displayName,
            sku
        ));
        completion.setWeight(Math.max(1, popularityWeight));
        this.suggest = completion;
    }

    // Constructors, getters and setters
}
~~~

Indexer:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductSuggestionIndexer {

    private final ElasticsearchOperations operations;

    public ProductSuggestionIndexer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void index(ProductSuggestionDocument document, int popularity) {
        document.buildSuggestion(popularity);
        operations.save(document);
    }
}
~~~

Suggestion search service:

~~~java
import co.elastic.clients.elasticsearch.core.search.Suggester;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductAutocompleteService {

    private final ElasticsearchOperations operations;

    public ProductAutocompleteService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductSuggestionDocument> suggest(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }

        String normalizedPrefix = prefix.strip();

        Suggester suggester = Suggester.of(s -> s
            .suggesters("product-autocomplete", field -> field
                .prefix(normalizedPrefix)
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

        return operations.search(
            query,
            ProductSuggestionDocument.class
        );
    }
}
~~~

Reading options:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.suggest.response.CompletionSuggestion;

public List<String> getSuggestionTexts(
        SearchHits<ProductSuggestionDocument> results) {

    List<String> values = new ArrayList<>();

    if (results.getSuggest() == null) {
        return values;
    }

    var rawSuggestion =
        results.getSuggest().getSuggestion("product-autocomplete");

    if (rawSuggestion instanceof CompletionSuggestion<?> completion) {
        for (CompletionSuggestion.Entry<?> entry : completion.getEntries()) {
            for (CompletionSuggestion.Entry.Option<?> option : entry.getOptions()) {
                values.add(option.getText());
            }
        }
    }

    return values;
}
~~~

This example keeps indexing data, building the suggester, and reading suggestion options as strings for the UI to display. If the UI needs product IDs or details, read option.getSearchHit() when source is present or use the document ID to load details.

## 18. Implementation Workflow

When adding autocomplete with Completion suggester:

1. Identify the types of inputs users need suggested: names, aliases, codes, brands, or places.
2. Create a field with mapping type completion using @CompletionField.
3. Choose analyzer, search analyzer, separator behavior, and max input length.
4. Design a pipeline for normalization, deduplication, and input generation.
5. Define how weights are calculated and updated.
6. If filtering by category or location is needed, declare context mappings before creating the index.
7. Index completion data via Spring Data or a bulk pipeline.
8. Use NativeQuery.withSuggester(...) to send prefix/fuzzy/context options.
9. Read results via SearchHits.getSuggest() and convert to DTOs.
10. Limit source, option count, and prefix length.
11. Test mapping, inputs, contexts, duplicate behavior, and refresh.
12. Monitor heap, latency, completion index size, and user suggestion click-through rate.
13. Sync suggestion documents when business data changes or is deleted.

Completion suggester delivers fast autocomplete when input data is prepared intentionally. Mappings determine analysis and lookup structures; inputs and weights determine content and suggestion order; contexts filter or boost by context. Spring Data Elasticsearch connects these pieces via Completion, @CompletionField, NativeQuery, and SearchHits.getSuggest().

## 19. References

- [Elasticsearch - Completion suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters): mapping, input, weight, prefix, fuzzy, duplicate handling, and contexts.
- [Elasticsearch - Completion field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/completion): analyzer, separators, and max input length.
- [Elasticsearch - Context suggester](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/search-suggesters#context-suggester): category context and geo context.
- [Spring Data Elasticsearch API - CompletionField](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/CompletionField.html): completion mapping attributes.
- [Spring Data Elasticsearch API - Completion](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/suggest/Completion.html): input, weight, and contexts in Spring Data's model.
- [Spring Data Elasticsearch API - NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html): configuring suggesters with the Elasticsearch Java API Client.
- [Spring Data Elasticsearch API - SearchHits](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html): accessing the suggest response.

Package names and builder methods may vary across Spring Data Elasticsearch and Elasticsearch Java API Client versions. When implementing, verify Javadocs against the dependencies managed in your project.
