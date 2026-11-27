# Term, Terms, and Differences from Match

Elasticsearch provides several query types to find documents. Three queries that are frequently confused are term, terms, and match:

- **term** searches for an indexed value by matching a single term exactly.
- **terms** finds documents whose field matches at least one value from a supplied list.
- **match** analyzes the query string using the field's analyzer and then searches for the resulting tokens.

The key point is that "exact" in Elasticsearch depends on the mapping and the analysis process. A keyword field usually preserves the value intact for exact filtering. A text field is usually split and normalized into tokens by an analyzer for full-text search. Therefore, choosing the right query must start from the actual field type and mapping, not merely from the method name or the shape of the input string.

## 1. Three Queries Solving Three Different Needs

Suppose the products index contains documents:

~~~json
{
  "sku": "SKU-1001",
  "name": "Wireless Mouse",
  "status": "ACTIVE"
}
~~~

The corresponding requirements:

| Requirement | Commonly used query |
|---|---|
| Find product with SKU equal to SKU-1001 | term |
| Find products with status ACTIVE or IN_STOCK | terms |
| Find products whose name relates to wireless mouse | match |
| Find names containing the phrase wireless mouse in order | match_phrase |

REST API examples:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "status": ["ACTIVE", "IN_STOCK"]
    }
  }
}
~~~

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Even though each uses a JSON string, Elasticsearch handles the value differently for each query.

## 2. Term Query: Matching a Single Term

term is a term-level query. It finds documents whose indexed value matches the specified value.

Example:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "sku": "SKU-1001"
    }
  }
}
~~~

If sku is mapped as keyword, this query finds the corresponding SKU value. A term query does not run an analyzer to split the query string into tokens like a match query does.

Common use cases:

- SKUs, order codes, customer IDs.
- Statuses such as ACTIVE, PENDING, CANCELLED.
- Emails or usernames when matching semantics are clearly defined.
- Boolean, numeric, or date values.
- A keyword value requiring exact matching.

### 2.1. Term does not mean literal comparison with _source in all cases

Elasticsearch searches against indexed terms rather than comparing the input string directly against the JSON _source.

For example, a keyword field configured with a lowercase normalizer:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "username": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Indexed document:

~~~json
{
  "username": "Alice"
}
~~~

The indexed term after the normalizer is alice. For a keyword field with a normalizer, Elasticsearch applies the normalizer at search time for applicable queries, including term-level queries on that field. Therefore, the following query can match:

~~~http
POST /users/_search
{
  "query": {
    "term": {
      "username": "ALICE"
    }
  }
}
~~~

Meanwhile, _source still retains the original spelling "Alice". A normalizer changes how the field is indexed and searched; it does not overwrite the original content in _source.

If a keyword field has no normalizer, values are typically case-sensitive. Check the mapping before inferring results.

### 2.2. Term on a text field

Do not use term as if it were a match query for a text field.

Suppose the mapping is:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    }
  }
}
~~~

With the standard analyzer, the string "Wireless Mouse" can be analyzed into tokens:

~~~text
Wireless Mouse
      |
      v
wireless, mouse
~~~

Query:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "name": "Wireless Mouse"
    }
  }
}
~~~

usually does not match, because a term query does not analyze the query string into two tokens. It searches for a single term matching the supplied value. Conversely, a term query with "wireless" can match the token indexed by the analyzer:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "name": "wireless"
    }
  }
}
~~~

This usage requires the query author to know the exact tokens produced by the analyzer. For ordinary text search, match is usually more appropriate.

## 3. Terms Query: Matching One of Multiple Values

The terms query accepts a list of values. A document matches if the field has at least one value matching any value in the list.

Example:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "status": ["ACTIVE", "IN_STOCK", "BACKORDER"]
    }
  }
}
~~~

Logically, the condition is roughly equivalent to:

~~~text
status = ACTIVE
OR status = IN_STOCK
OR status = BACKORDER
~~~

terms is commonly used to:

- Filter by multiple acceptable statuses.
- Find documents belonging to a set of IDs.
- Filter by a list of SKUs or category codes.
- Apply an application-defined set of values.

### 3.1. Terms does not require all values to match

Example:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "category": ["accessories", "computer", "office"]
    }
  }
}
~~~

Documents with category accessories, computer, or office can all match. The query does not require a single document to have all three values.

If business logic requires a document to satisfy multiple independent conditions, use a bool query with corresponding conditions, or terms_set if you need semantics around how many values match on a multi-valued field.

### 3.2. Terms on an array field

A keyword field can hold multiple values:

~~~json
{
  "tags": ["wireless", "bluetooth", "accessory"]
}
~~~

Query:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "tags": ["bluetooth", "gaming"]
    }
  }
}
~~~

A document matches if the tags array contains bluetooth or gaming. Only one value in the query list needs to match one value in the field.

If a document must contain both bluetooth and wireless at the same time, combine two term queries using bool must (or filter):

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tags": "bluetooth"
          }
        },
        {
          "term": {
            "tags": "wireless"
          }
        }
      ]
    }
  }
}
~~~

### 3.3. Limit on the number of values in terms

Elasticsearch limits the number of values in a terms query. A common default is 65,536 values, controlled by the index setting index.max_terms_count. The actual limit may be configured differently on your cluster.

Do not send a list of hundreds of thousands or millions of values in a single query without evaluating limits and cost. For large ID sets, consider batching, using terms lookup, or changing the query design.

### 3.4. Terms lookup

Elasticsearch can fetch the value list for a terms query from another document instead of sending the entire list in the request. This mechanism is called terms lookup.

Example:

~~~http
POST /products/_search
{
  "query": {
    "terms": {
      "sku": {
        "index": "saved-filters",
        "id": "filter-1001",
        "path": "skus"
      }
    }
  }
}
~~~

Elasticsearch reads the skus field from document filter-1001 in index saved-filters and uses those values for the terms query.

Terms lookup is suitable when filter lists are pre-stored in Elasticsearch and reused. Ensure the source document exists, the field path is correct, permissions are appropriate, and related cluster conditions are met. For small lists, passing the values array directly is usually simpler.

## 4. Match Query: Search with Text Analysis

match is a full-text query. Before searching, Elasticsearch analyzes the query string using the field's analyzer (or an analyzer specified in the query).

Example text field name:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "analyzer": "standard"
    }
  }
}
~~~

Query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "Wireless Mouse"
    }
  }
}
~~~

With an appropriate analyzer, the query string can be normalized and split into tokens wireless and mouse. Elasticsearch searches for documents based on these tokens.

Match is suitable for:

- Product names.
- Descriptions.
- Article titles.
- Document bodies.
- Text fields searched by words or phrases.

### 4.1. OR and AND operators

By default, match queries typically use the OR operator across analyzed tokens. For instance, querying "wireless mouse" can match documents containing wireless or mouse, depending on the analyzer and query options.

You can require all tokens to match:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": {
        "query": "wireless mouse",
        "operator": "and"
      }
    }
  }
}
~~~

With operator AND, documents must satisfy all tokens produced from the query under an AND condition. This still does not mean the two words must be adjacent or in exact order.

### 4.2. minimum_should_match

If you want finer control over how many tokens must match than AND/OR provides, use minimum_should_match:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": {
        "query": "wireless bluetooth ergonomic mouse",
        "minimum_should_match": "75%"
      }
    }
  }
}
~~~

Depending on the calculation and token count after analysis, 75% requires a certain proportion of tokens to match. This option is useful when queries have many words and you want to balance recall against strictness.

### 4.3. Match is not synonymous with exact phrase

Query:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

does not guarantee the two words appear next to each other in exact order. If you need a phrase search, use match_phrase:

~~~http
POST /products/_search
{
  "query": {
    "match_phrase": {
      "name": "wireless mouse"
    }
  }
}
~~~

match_phrase still uses analysis and token positions. It is not a byte-for-byte literal string comparison against _source. If an exact value is needed, use an appropriate keyword field.

## 5. Key Differences Between term, terms, and match

| Criterion | term | terms | match |
|---|---|---|---|
| Query type | Term-level | Term-level | Full-text |
| Input cardinality | Single value | A list | A query string |
| Analyzes query with analyzer | No | No | Yes |
| Default logic | One term must match | Any value in the list matches | OR across tokens is usually the default |
| Common field types | keyword, numeric, boolean, date | keyword, ID, numeric, boolean, date | text |
| Used for | Exact filter | Exact filter against a value set | Content search |
| Handles keyword normalizer | Yes, per mapping/query behavior | Yes, per mapping/query behavior | Field analyzer/normalizer applies per query semantics |

In summary:

- term: a single indexed value.
- terms: one of multiple indexed values.
- match: analyzes the query string into tokens and searches text.

## 6. How Mapping Determines Query Behavior

An entity may need both full-text search and exact filtering on the same attribute. Multi-fields allow indexing the same value in multiple ways.

Example:

~~~http
PUT /products
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "sku": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "price": {
        "type": "long"
      }
    }
  }
}
~~~

This mapping creates:

- name: text for match.
- name.keyword: keyword for exact filter, sort, or aggregation.
- sku: keyword for exact SKU lookup.
- status: keyword for filtering multiple statuses with terms.
- price: long for numeric range or term queries.

Full-text search example:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Exact name lookup:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Mouse"
    }
  }
}
~~~

If the keyword field has a normalizer, exact matching results will follow the normalized value. Inspect the mapping before choosing between name and name.keyword.

### 6.1. You cannot turn text into keyword just by changing the query

If name is currently text, running a term query with the full string does not turn the field into keyword. Conversely, running match on a keyword field does not generate tokens like a text field; the keyword analyzer typically keeps the entire value as one token.

To support both search modes, declare a multi-field upfront or update the mapping through an appropriate workflow. When adding a multi-field to existing data, you must update/reindex existing documents so values are indexed into the new field.

## 7. Distinguishing term from match on a keyword Field

A keyword field typically uses the keyword analyzer, meaning the entire string is treated as a single token. Therefore, match on a keyword field can behave almost like exact matching instead of full-text search.

Example:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "sku": "SKU-1001"
    }
  }
}
~~~

If sku is keyword, the query string is generally processed as a single value. Still, when the intent is to filter for an exact code, term expresses that intent more clearly.

Do not use match on a keyword field expecting substring search. If you need prefix or wildcard matching, use an appropriate query such as prefix or wildcard on the keyword field and consider the cost.

## 8. Term, terms, and Data Types

Term-level queries are not just for strings. They are also useful for data types whose values are indexed directly.

### 8.1. Numbers

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "price": 259900
    }
  }
}
~~~

Finds documents with price equal to 259900. If you need a price interval, use a range query:

~~~http
POST /products/_search
{
  "query": {
    "range": {
      "price": {
        "gte": 100000,
        "lte": 500000
      }
    }
  }
}
~~~

### 8.2. Boolean

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "active": true
    }
  }
}
~~~

### 8.3. Date

~~~http
POST /orders/_search
{
  "query": {
    "term": {
      "status": "PAID"
    }
  }
}
~~~

For date-times, a range query is typically used to express time intervals. Ensure formats and timezones match the mapping.

### 8.4. ID

You can use the ids query when looking up multiple documents by _id:

~~~http
POST /products/_search
{
  "query": {
    "ids": {
      "values": ["P-1001", "P-1002", "P-1003"]
    }
  }
}
~~~

This is a specialized query for document IDs. If you need to filter by an ID field stored in _source, inspect the field mapping and pick term/terms accordingly.

## 9. Bool Query to Combine term, terms, and match

In real applications, queries are commonly combined. For example, finding products matching "wireless mouse", status in ACTIVE or IN_STOCK, and price at most 500,000:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": {
              "query": "wireless mouse",
              "operator": "and"
            }
          }
        }
      ],
      "filter": [
        {
          "terms": {
            "status": ["ACTIVE", "IN_STOCK"]
          }
        },
        {
          "range": {
            "price": {
              "lte": 500000
            }
          }
        }
      ]
    }
  }
}
~~~

In this example:

- must contains match to search text and participate in relevance scoring.
- filter contains terms and range for exact filtering without scoring those conditions.

When a keyword condition is only used to narrow the result set, filter is generally more appropriate than must. This clarifies the purpose of each condition and can leverage filter caching where applicable.

## 10. Integrating with Spring Data Elasticsearch

You can use ElasticsearchOperations together with NativeQuery to build term-level and full-text queries. The examples below use Spring Data Elasticsearch 5.x with the Elasticsearch Java API Client.

### 10.1. Term query using NativeQuery

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query termQuery = Query.of(q -> q
    .term(t -> t
        .field("sku")
        .value(FieldValue.of("SKU-1001"))
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(termQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

FieldValue and Query in this example belong to the Elasticsearch Java API Client, not Spring Data Criteria API's Query.

### 10.2. Terms query using NativeQuery

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

List<FieldValue> statuses = List.of(
    FieldValue.of("ACTIVE"),
    FieldValue.of("IN_STOCK")
);

Query termsQuery = Query.of(q -> q
    .terms(t -> t
        .field("status")
        .terms(tf -> tf.value(statuses))
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(termsQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

The values list has OR semantics: a document matches if status equals any of the values. With a large number of values, keep terms query limits and request size in mind.

### 10.3. Match query using NativeQuery

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Operator;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query matchQuery = Query.of(q -> q
    .match(m -> m
        .field("name")
        .query(FieldValue.of("wireless mouse"))
        .operator(Operator.And)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(matchQuery)
    .build();

SearchHits<Product> hits =
    operations.search(nativeQuery, Product.class);
~~~

Operator.And requires tokens produced by the analyzer to match per match query semantics. It does not require the phrase to be contiguous; if you need a phrase, use match_phrase.

Builder methods may vary across minor versions. Verify imports and API signatures against the Spring Data Elasticsearch and Elasticsearch Java API Client versions in your project.

## 11. Do Derived Repository Methods Replace term/terms/match?

Spring Data Elasticsearch supports derived query methods, for example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findBySku(String sku);

    List<Product> findByStatusIn(Collection<String> statuses);

    List<Product> findByName(String name);
}
~~~

Method names let Spring Data derive queries from properties and predicates. However, do not assume:

- findBySku always compiles to the exact JSON term query in every version.
- findByStatusIn is always completely identical to a terms query in every case.
- findByName always has the desired full-text semantics just because the field is named name.

The outcome depends on the Spring Data Elasticsearch version, mappings, and supported query derivation. If you need explicit control over term, terms, or match DSL, use @Query or NativeQuery and inspect the actual request.

Example @Query for a fixed term condition:

~~~java
@Query("{\"term\":{\"sku\":\"?0\"}}")
List<Product> findExactSku(String sku);
~~~

For dynamic queries or multi-condition combinations, NativeQuery/ElasticsearchOperations is usually easier to control than assembling JSON strings inside annotations.

## 12. Inspecting Analyzers with the Analyze API

When match or term on a text field yields unexpected results, check which tokens the analyzer produces.

Example:

~~~http
POST /products/_analyze
{
  "field": "name",
  "text": "Wireless Mouse"
}
~~~

The response may contain tokens:

~~~json
{
  "tokens": [
    {
      "token": "wireless",
      "position": 0
    },
    {
      "token": "mouse",
      "position": 1
    }
  ]
}
~~~

Specific output depends on the analyzer mapped to the field. If a custom analyzer, lowercase filter, stemming, or synonyms are used, tokens may differ.

The Analyze API helps explain:

- Why match with uppercase still finds results.
- Why term with the full phrase fails to match a text field.
- Why base words and stemmed words can match each other.
- Why punctuation or special characters are split/normalized.

You can specify an analyzer directly in the Analyze API when testing a specific configuration, but when debugging production queries, inspect the analyzer attached to the field in the mapping.

## 13. Case Sensitivity and Normalizers

For keyword fields, the default behavior is typically case-sensitive. Example:

~~~json
{
  "username": "Alice"
}
~~~

With a keyword field without a normalizer:

~~~http
POST /users/_search
{
  "query": {
    "term": {
      "username": "alice"
    }
  }
}
~~~

may not match because the casing differs.

You can declare a lowercase normalizer on keyword if the business requires case-insensitive lookup. Then both indexed values and query values are normalized according to the mapping.

For text fields, analyzers usually include a lowercase filter, so match queries can find content regardless of casing. A term query on text does not run the analyzer on the query value, so the author must know how tokens were normalized.

Do not blindly add lowercase or asciifolding to every field. Some identifiers have case- or diacritic-sensitive semantics. Choose rules according to business requirements.

## 14. Common Mistakes

| Symptom | Possible cause | How to check |
|---|---|---|
| term with full phrase does not match text field | Analyzer split text into multiple tokens | Use Analyze API and appropriate match/match_phrase |
| term is unexpectedly case-sensitive | Keyword lacks a normalizer or token casing differs | Inspect mapping and normalizer |
| terms returns more results than expected | Query uses OR across values | Confirm whether AND or terms_set is needed |
| terms misses some values | Type mismatch, character mismatch, normalizer, or wrong field | Inspect mapping and actual values |
| match returns results with one word missing | Default OR operator | Use operator AND or minimum_should_match |
| match does not enforce word order | Match is not a phrase query | Use match_phrase |
| match on keyword does not find substrings | Keyword is usually a single intact token | Use a text field or prefix/wildcard depending on requirements |
| Large terms query is rejected | Exceeds index.max_terms_count or request size limit | Batch requests, use terms lookup, or adjust design |
| Query behaves wrongly on an old index | Mapping/analyzer changed without reindexing existing data | Inspect mapping and migration state |
| Derived query lacks desired semantics | Version or predicate support differences | Use @Query/NativeQuery and inspect the actual API request |

## 15. Query Selection Workflow

When building a query, you can follow this sequence:

1. Identify whether the field is mapped as keyword, text, numeric, boolean, or date.
2. If you need to match a single indexed value, use term.
3. If you need to match one of several values, use terms.
4. If you need to search text content through an analyzer, use match.
5. If words must appear as an ordered phrase, use match_phrase.
6. If all tokens must match, use operator AND or an appropriate minimum_should_match.
7. If the query returns unexpected results, inspect mapping, normalizer, and the Analyze API.
8. If you need precise DSL control from Spring Data, use NativeQuery or @Query.

## 16. Quick Reference Table

| Requirement | Query |
|---|---|
| Exact SKU | term on keyword |
| One of several statuses | terms on keyword |
| One of several IDs | ids or terms depending on field |
| Price equals a specific number | term on numeric field |
| Price within a range | range |
| Search content by words | match on text |
| All tokens must match | match with operator AND |
| Ordered phrase search | match_phrase |
| Exact original value of a text multi-field | term on .keyword field |
| Case-insensitive keyword lookup | term on keyword with lowercase normalizer |
| Match one of a large set stored in Elasticsearch | terms lookup |
| Combine full-text and exact filter | bool with must match and filter term/terms |

term, terms, and match are not interchangeable. term searches for a single indexed term, terms matches documents matching one of several values, and match analyzes the query string into tokens for full-text search. Choose queries based on field mappings and analyzers: keyword for exact filtering, text for full-text, and multi-fields when a single value needs both. In Spring Data Elasticsearch, use NativeQuery or @Query when explicit DSL control is required, and inspect actual analyzers/mappings whenever results differ from expectations.
