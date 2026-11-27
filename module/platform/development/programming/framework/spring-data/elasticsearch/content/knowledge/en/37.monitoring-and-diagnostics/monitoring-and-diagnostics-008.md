# Sorting Errors, Aggregations on Text, and Fielddata Limits

A common error when using Elasticsearch is trying to sort or run a terms aggregation on a text field. The request may return a message like "Fielddata is disabled on text fields by default". This error does not mean Elasticsearch cannot sort strings; it indicates the queried field is designed for full-text search and lacks an appropriate structure for value-based sorting/aggregation.

The usually correct fix is creating a keyword multi-field for the same data, then using that subfield for sorting, terms aggregations, or exact filters. Fielddata can be enabled on text in special cases, yet fielddata is loaded into heap and can consume large amounts of memory, increasing garbage collection or tripping circuit breakers.

In Spring Data Elasticsearch, you must declare mappings accurately from the start, use the right field names in queries, and inspect the actual mapping on the cluster. This lesson explains the cause of the error, how fielddata works, memory limits, the keyword solution, handling legacy data, examples with Spring Data and Elasticsearch APIs, and monitoring and diagnostic steps.

## 1. Why do sorting and aggregations on text usually fail?

Text fields are designed for full-text search. When indexed, an analyzer splits content into tokens and may normalize casing, punctuation, or stop words.

Example:

~~~text
Original value: "Wireless Ergonomic Mouse"
Analyzer:
  wireless
  ergonomic
  mouse
~~~

Elasticsearch stores tokens in an inverted index to find documents by word. This structure suits match queries, but it is not an optimal representation for retrieving the full value of each document to sort or group.

Example sort request:

~~~http
GET products/_search
{
  "sort": [
    {
      "name": {
        "order": "asc"
      }
    }
  ]
}
~~~

If name is text and fielddata is not enabled, Elasticsearch usually returns an error similar to:

~~~text
Fielddata is disabled on [name] in [products].
Text fields are not optimised for operations that require per-document field data
like aggregations and sorting, so these operations are disabled by default.
Please use a keyword field instead.
Alternatively, set fielddata=true on [name] in order to load field data by uninverting the inverted index.
~~~

Terms aggregation on text can hit the same issue:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "names": {
      "terms": {
        "field": "name"
      }
    }
  }
}
~~~

This is a mapping/query mismatch. Elasticsearch is being asked to operate on per-document values of a field configured primarily for token-based search.

## 2. text, keyword, and data access patterns

The two common string field types have different semantics.

| Characteristic | text | keyword |
|---|---|---|
| Analyzer/tokenization | Yes | Not tokenized like text |
| Full-text match | Suitable | Primarily exact term |
| Exact filter | Usually needs another representation | Suitable |
| Sort by value | Fielddata can be enabled, but costs heap | Doc values usually available |
| Terms aggregation | Needs fielddata or another field | Doc values usually available |
| Data viewed as | Analyzed tokens | Whole value normalized per normalizer |

Example mapping:

~~~json
{
  "properties": {
    "name": {
      "type": "text"
    },
    "category": {
      "type": "keyword"
    }
  }
}
~~~

With this mapping:

- name fits match queries.
- category fits term filters, sorts, and terms aggregations.
- Do not use name for sorting or aggregating by full product name.

If a value needs both full-text search and sorting/aggregation, use a multi-field.

## 3. Multi-field is the default solution for strings needing multiple access patterns

A multi-field allows indexing the same value in multiple representations. For example, name is the main text field and name.keyword is a keyword sub-field.

~~~json
PUT products-v2
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      }
    }
  }
}
~~~

When indexing a document, Elasticsearch produces:

- name: tokenized for full-text search.
- name.keyword: kept intact for exact match, sorting, and aggregation.

Full-text queries continue using name:

~~~http
GET products/_search
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
~~~

Sorting uses name.keyword:

~~~http
GET products/_search
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

Terms aggregation uses name.keyword:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "names": {
      "terms": {
        "field": "name.keyword",
        "size": 20
      }
    }
  }
}
~~~

Exact filters also use the sub-field:

~~~http
GET products/_search
{
  "query": {
    "term": {
      "name.keyword": "Wireless Ergonomic Mouse"
    }
  }
}
~~~

Exact matches on keyword still obey normalizer rules if the field configures a normalizer. Without a normalizer, differences in casing and whitespace can affect results.

### 3.1. Choosing sub-field names

A common name is keyword, though you can name sub-fields to express intent:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "raw": {
        "type": "keyword",
        "ignore_above": 256
      },
      "sort": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Then:

- name is used for full-text.
- name.raw is used for original exact values.
- name.sort is used for normalized values when sorting.

Do not create extra sub-fields without a use case. Every additional representation adds storage, indexing, and merge costs.

### 3.2. ignore_above and long values

Keyword fields can limit indexed value length with ignore_above. For example, ignore_above: 256 means values longer than the limit are not indexed into the keyword sub-field.

The value remains in _source and the main text field remains full-text searchable. However, that document has no corresponding term/doc value in the sub-field, so it may not participate in sorting or aggregation as expected.

Pick the limit based on real data. For long strings unsuitable as categories or sort keys, consider using a different field instead of setting a very large limit arbitrarily.

## 4. How do doc values help sorting and aggregations?

Keyword fields usually have doc values enabled by default. Doc values store values in a document-to-value column-oriented layout, suited for reading fields across sets of documents.

Example category:

~~~json
{
  "category": {
    "type": "keyword"
  }
}
~~~

Aggregation:

~~~json
{
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Sort:

~~~json
{
  "sort": [
    {
      "category": {
        "order": "asc"
      }
    }
  ]
}
~~~

Doc values are generally stored on disk and leverage the filesystem cache. They do not imply loading all values into Java heap like fielddata.

This does not mean sorting and aggregations use zero memory. Aggregations still need memory for buckets and intermediate results; sorting processes values and top hits. Doc values simply provide an appropriate representation for field access.

## 5. What is fielddata?

Fielddata is an in-memory data structure built by Elasticsearch from the inverted index to provide per-document values for operations such as sorting, aggregations, or scripts on certain fields, particularly text.

When enabling fielddata on text:

~~~json
PUT products/_mapping
{
  "properties": {
    "name": {
      "type": "text",
      "fielddata": true
    }
  }
}
~~~

Elasticsearch can uninvert the inverted index to build fielddata. This process can load many terms and term-document relationships into heap.

Fielddata differs from doc values:

| Characteristic | Fielddata on text | Doc values |
|---|---|---|
| Source/representation | Built from the inverted index | Columnar structure built at index time |
| Memory | Can consume significant JVM heap | Primarily stored on disk, uses filesystem cache |
| Purpose | Enables sort/aggregation on text when turned on | Sort/aggregation on supported field types |
| Cost | Incurred when fielddata is loaded | Storage/indexing cost at write time |
| Key risk | Heap pressure and fielddata circuit breaker | Disk/cache and bucket/sort costs still apply |

Fielddata can be cached after loading. The first query can incur a heavy build cost; subsequent queries can reuse the cache until segments/caches change or are cleared/evicted.

### 5.1. Fielddata does not store just one string per document

For text, an analyzer can emit many tokens per field. Fielddata may need to represent many terms and document associations. A long description field with many tokens and many documents can create a large footprint.

Example description:

~~~text
"Wireless mouse with ergonomic design and rechargeable battery"
~~~

The analyzer can emit many tokens. Aggregating on this field normally groups by analyzed tokens rather than the full description sentence. Results may both miss business intent and consume heap.

If the goal is grouping by full description values, a keyword multi-field fits the semantics better, though length and cardinality must be considered.

### 5.2. Fielddata can increase heap usage and GC

When fielddata occupies a lot of heap:

- Garbage collection can run more frequently.
- Search latency can climb.
- Nodes can experience memory pressure.
- Circuit breakers can reject loading fielddata or requests.
- Nodes can become unstable if memory is overcommitted.

Fielddata is managed at the node level and can span multiple shards on the same node. A query on an index can trigger fielddata loading across every shard the query touches.

## 6. Why does Elasticsearch disable fielddata on text by default?

Elasticsearch chooses a safe default because sorting/aggregating on text is rarely the primary use case and can cause unpredictable heap costs.

If every text field automatically loaded fielddata on aggregation, a single new dashboard or query could spike heap usage in production.

The error message advising you to use a keyword field is appropriate advice in most cases:

- Full-text search: text.
- Exact/sort/aggregation: keyword.
- Both needed: multi-field.

Enabling fielddata is a deliberate choice for cases needing operations on analyzed tokens, after measuring memory and controlling queries.

## 7. When might fielddata be justified?

Some specialized use cases require aggregating or sorting on analyzed tokens. Examples:

- Computing token frequency statistics in content.
- Analyzing post-analyzer keywords.
- Search relevance or linguistic data research.
- A short text field with controlled cardinality and document count where aggregation semantics genuinely require tokens.

Even in those cases, make sure it is clear whether the aggregation groups by tokens or whole values. Fielddata does not turn text into keyword; it provides per-document data from text tokens.

Before enabling it, evaluate:

1. Number of documents containing the field.
2. Average length and token count per document.
3. Token cardinality.
4. Number of shards and nodes that may load fielddata.
5. Actual heap size and peak utilization.
6. Number of queries that could trigger fielddata.
7. Impact when caches are cold or segments merge.

If the goal is simply sorting by name or grouping by category, use a keyword multi-field.

## 8. Fielddata frequency filter

Elasticsearch can support configuring a fielddata frequency filter for text fields to restrict which terms are loaded into fielddata, depending on the version.

Illustrative example:

~~~json
{
  "name": {
    "type": "text",
    "fielddata": true,
    "fielddata_frequency_filter": {
      "min": 0.01,
      "max": 0.5,
      "min_segment_size": 500
    }
  }
}
~~~

This filter relies on term frequency per segment and can skip terms that are too rare or too common based on configured thresholds. It does not turn fielddata into doc values and does not guarantee fixed memory usage.

Verify setting names, threshold meanings, and support on the Elasticsearch version in use. Measure results against real data before deploying to production.

## 9. Fielddata circuit breaker

Elasticsearch uses circuit breakers to prevent operations estimated to exceed configured memory limits.

The fielddata circuit breaker monitors fielddata loading. If estimated new memory exceeds the limit, Elasticsearch can reject the operation and return a circuit breaking error instead of letting heap keep growing.

Related settings may include:

- indices.breaker.fielddata.limit
- indices.breaker.fielddata.overhead
- indices.breaker.request.limit
- indices.breaker.total.limit

Names, defaults, and semantics depend on the Elasticsearch version. Do not raise breaker limits just to make a query pass without understanding the source of memory pressure.

### 9.1. Circuit breakers are not performance optimizers

Circuit breakers are a protective mechanism. If queries repeatedly trip breakers, raising limits can push nodes closer to OOM.

Before adjusting:

- Identify which field is loading fielddata.
- Identify which query/aggregation triggers it.
- Check fielddata memory per node.
- Check heap usage, GC, and request concurrency.
- Evaluate whether a keyword multi-field can be used.
- Reduce bucket cardinality or data scope where appropriate.

Adjust breaker limits only after evaluating heap headroom, concurrent load, and impact on other workloads.

## 10. How to fix sorting errors on text

### 10.1. Identify the actual mapping

Read the mapping:

~~~http
GET products/_mapping
~~~

Locate the field being sorted. If the field is:

~~~json
{
  "name": {
    "type": "text"
  }
}
~~~

then sorting directly on name requires fielddata, which is disabled by default.

### 10.2. Check if a keyword sub-field exists

If the mapping already has:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

switch the query sort to name.keyword:

~~~http
GET products/_search
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc"
      }
    }
  ]
}
~~~

### 10.3. Handling missing values and tie-breakers

If some documents lack the keyword sub-field, you can configure missing:

~~~json
{
  "sort": [
    {
      "name.keyword": {
        "order": "asc",
        "missing": "_last"
      }
    },
    {
      "_id": {
        "order": "asc"
      }
    }
  ]
}
~~~

A tie-breaker keeps ordering deterministic when multiple documents share the same name. For deep pagination, consider search_after and sorting on a stable key.

Do not use _id as a generic doc-values field for every sort pattern. If sorting by identifier is needed, map a dedicated keyword field holding the business ID and sort on that field.

## 11. How to fix aggregation errors on text

If an aggregation needs to group by whole values, use a keyword field:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category",
        "size": 50
      }
    }
  }
}
~~~

If the field is text with a keyword sub-field:

~~~http
GET products/_search
{
  "size": 0,
  "aggs": {
    "by_name": {
      "terms": {
        "field": "name.keyword",
        "size": 20
      }
    }
  }
}
~~~

If you genuinely need token-level aggregation, you can enable fielddata after evaluation:

~~~json
PUT products/_mapping
{
  "properties": {
    "description": {
      "type": "text",
      "fielddata": true
    }
  }
}
~~~

However, terms aggregation results then reflect analyzed tokens rather than full description strings. For example, descriptions with "wireless mouse" and "wireless keyboard" produce buckets for tokens wireless, mouse, keyboard.

## 12. Fixing mappings in Spring Data Elasticsearch

Spring Data Elasticsearch supports declaring multi-fields using @MultiField and @InnerField.

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.InnerField;
import org.springframework.data.elasticsearch.annotations.MultiField;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(
            type = FieldType.Text,
            analyzer = "standard"
        ),
        otherFields = {
            @InnerField(
                suffix = "keyword",
                type = FieldType.Keyword,
                ignoreAbove = 256
            )
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    // getters and setters
}
~~~

Expected mapping:

~~~json
{
  "name": {
    "type": "text",
    "analyzer": "standard",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  },
  "category": {
    "type": "keyword"
  }
}
~~~

Queries must then reference the exact sub-field name.

Mapping annotations do not automatically alter existing cluster mappings simply because entity code changed. You must check index creation lifecycles, mapping updates, and your application's migration strategy.

### 12.1. Declaring fielddata in Spring Data

If a use case truly requires fielddata, the @Field annotation in a compatible Spring Data Elasticsearch version may provide the fielddata attribute:

~~~java
@Field(
    type = FieldType.Text,
    fielddata = true
)
private String analyzedTerms;
~~~

Confirm this attribute exists in your annotation version and verify the actual mapping after index creation.

Do not enable fielddata on all text fields by default. Enable it only on fields with evaluated and monitored token-level sort/aggregation requirements.

### 12.2. Using IndexOperations to inspect mapping

You can read mappings via IndexOperations:

~~~java
IndexOperations indexOperations =
    operations.indexOps(Product.class);

Map<String, Object> mapping =
    indexOperations.getMapping();
~~~

Method names and return types depend on version. In production diagnostics, the REST Mapping API remains the direct way to verify mappings on the live index.

## 13. Spring Data queries: sorts and aggregations using sub-fields

Example with ElasticsearchOperations and NativeQuery:

~~~java
NativeQuery query = NativeQuery.builder()
    .withSort(Sort.by(Sort.Order.asc("name.keyword")))
    .withQuery(QueryBuilders.matchQuery("name", "wireless mouse"))
    .build();
~~~

Query builders and query construction depend on the Spring Data Elasticsearch version. One option is using the Elasticsearch Java API Client Query DSL or request JSON when precise control is needed.

Aggregations on keyword fields can be expressed via the corresponding aggregation builder:

~~~json
{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

What to verify in code is the field path:

- Match query: name.
- Sort: name.keyword.
- Terms aggregation: name.keyword or category.
- Exact filter: name.keyword or category.

Do not replace every query using name with name.keyword. Full-text search still requires the text field.

## 14. New multi-fields do not automatically populate old documents

This is a common deployment mistake. The new mapping adds name.keyword, yet previously indexed documents are not automatically reprocessed.

Example old mapping:

~~~json
{
  "name": {
    "type": "text"
  }
}
~~~

New mapping adding the sub-field:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword",
        "ignore_above": 256
      }
    }
  }
}
~~~

Once the mapping is updated, new documents will have name.keyword. Old documents must be re-indexed to populate terms/doc values for the sub-field.

Two common approaches:

**Update by query**: reprocess existing documents in the same index to apply the new mapping, when suitable for requirements and update semantics.

~~~http
POST products/_update_by_query?conflicts=proceed
{
  "query": {
    "match_all": {}
  }
}
~~~

**Reindex to a new index**: create a destination index with the complete mapping and copy data:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2"
  }
}
~~~

Update by query can generate heavy load and hit version conflicts. Reindexing to a new index usually fits better for major schema changes or when clean rollback is needed.

After backfilling, verify old documents have keyword values, run sorts/aggregations, and confirm results.

## 15. Existing mapping types cannot be changed arbitrarily

If name is currently text and you want to convert it to keyword, you cannot simply change the type in the existing mapping. Create a new field/sub-field or a new index.

For complex analyzer, type, or structural changes:

1. Create a new index version.
2. Declare mappings and settings.
3. Reindex data.
4. Check document counts and field capabilities.
5. Run sort/aggregation queries on the new index.
6. Switch aliases or application configuration.
7. Retain a rollback plan per policy.

When only adding a multi-field, mapping updates may be supported, yet legacy data still needs backfilling. Do not confuse "mapping update succeeded" with "every document now has the new value".

## 16. Cardinality and aggregation size

Using the right keyword field alone is not enough to make aggregations cheap. A terms aggregation with high cardinality can create many buckets and consume memory.

For example, category with dozens of values is usually far lighter than customerEmail with millions of unique values.

Before aggregating, consider:

- Actual cardinality.
- Document count after filtering.
- Bucket size to return.
- Shard count.
- Sub-aggregations.
- Whether all buckets are needed or only top N.
- Whether composite aggregation can paginate buckets.
- Whether summaries can be precomputed in a separate index.

size caps returned buckets, yet it does not eliminate all shard-side processing costs. shard_size affects how many candidate buckets each shard returns to the coordinator. Tuning must balance accuracy and load.

With high cardinality and a need to iterate all buckets, composite aggregations can fit better than large terms aggregations.

## 17. Fielddata cache and monitoring tools

To see where fielddata is used, inspect cluster metrics.

### 17.1. CAT fielddata

~~~http
GET _cat/fielddata?v
~~~

Can filter by field:

~~~http
GET _cat/fielddata/name,description?v
~~~

The output helps identify which fields hold fielddata and associated memory per node.

### 17.2. Node stats

~~~http
GET _nodes/stats/indices/fielddata
~~~

Per-field breakdowns may be viewed if your API version supports the corresponding fields query parameter.

Monitor:

- Fielddata memory size.
- Fielddata evictions.
- Heap usage.
- Old generation pressure.
- GC counts/times.
- Search latency.
- Circuit breaker trips.
- Node restarts.

### 17.3. Circuit breaker stats

~~~http
GET _nodes/stats/breaker
~~~

Check breaker counts, estimated sizes, and limits per your version's response. If breakers trip frequently, identify the offending queries and fields before raising limits.

### 17.4. Query profiling

The Profile API can help inspect query/aggregation execution:

~~~http
GET products/_search
{
  "profile": true,
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Profiling has overhead and should not be enabled for all production requests. Combine profiling with metrics, slow logs, and end-to-end latency measurements.

## 18. Does clearing the fielddata cache fix the error?

Elasticsearch has a cache-clear API, for example:

~~~http
POST products/_cache/clear?fielddata=true
~~~

This command frees fielddata caches associated with the specified index. It can be useful when:

- Freeing cache during controlled operational intervention.
- Data/mapping changed under a procedure requiring cache cleanup.
- Investigating or mitigating a specific situation.

However, clearing cache does not fix mappings and does not eliminate the query requesting fielddata. The very next query can reload fielddata and cause the same memory pressure.

Do not run cache clear periodically as a performance optimization. It forces subsequent queries to rebuild caches, causing latency spikes.

## 19. Common wrong fixes

| Fix | Why it is problematic | Proper direction |
|---|---|---|
| Enabling fielddata on every text field | Can sharply increase heap usage | Enable only when token-level aggregation is needed |
| Increasing heap immediately on error | Does not fix mapping/query mismatch | Use keyword multi-fields |
| Raising fielddata breaker limits | Can push nodes toward OOM | Identify fields/queries causing memory pressure |
| Sorting directly on text | No doc values by default | Sort by keyword sub-field |
| Aggregating text to count whole strings | Actually groups by tokens | Use keyword representation |
| Clearing fielddata cache repeatedly | Cache reloads and causes spikes | Fix mapping and query |
| Adding multi-field without backfilling | Old docs lack the sub-field | Update by query or reindex |
| Editing only Java annotations | Live cluster mapping may not change | Inspect and migrate index |
| Setting unbounded terms size | Creates many buckets and uses memory | Fetch top N only or use composite aggregation |
| Making every long text a keyword | Cardinality/disk/indexing may grow sharply | Create sub-fields only per use case |

## 20. Testing mappings and queries in the application

Maintain integration tests verifying mapping and query behavior rather than testing only entity annotations.

A scenario:

1. Create a test index with mapping name text + name.keyword.
2. Index several products with different names.
3. Run a match query on name.
4. Run a sort on name.keyword.
5. Run a terms aggregation on name.keyword.
6. Confirm queries do not require fielddata on name.
7. Add a document with name longer than ignore_above.
8. Verify keyword sub-field behavior on long values.
9. If testing migration, backfill legacy documents and re-run queries.

Example data:

~~~json
[
  { "name": "Wireless Mouse", "category": "Accessories" },
  { "name": "Mechanical Keyboard", "category": "Accessories" },
  { "name": "Office Chair", "category": "Furniture" }
]
~~~

Expected outcomes:

- Match "wireless" finds Wireless Mouse.
- Sort by name.keyword returns lexical order by keyword value.
- Terms aggregation on category returns Accessories and Furniture.
- No fielddata is loaded on name solely due to these sort/aggregation operations.

### 20.1. Intentionally testing the fielddata error

You can create a test index with only text mapping for name, run sort/aggregation on name, and assert the request is rejected under the current mapping. Then add a keyword multi-field on a new index or separate test index and verify queries using name.keyword succeed.

Do not depend on the exact full error message string in assertions because messages can vary across Elasticsearch versions. Assert exception/status types and meaningful content.

## 21. Production error diagnostic workflow

When receiving a sort or aggregation error on text:

1. Record index, field, query, and error type.
2. Inspect the actual mapping via _mapping.
3. Confirm whether the field is text or keyword.
4. Check whether the field has an appropriate multi-field.
5. If a keyword sub-field exists, switch the query to that field path.
6. If absent, determine whether adding a multi-field is possible or a new index version is required.
7. Plan backfilling/reindexing so old documents populate the sub-field.
8. Check cardinality and aggregation size.
9. If fielddata is already enabled, inspect CAT fielddata, node stats, and breaker stats.
10. Evaluate heap, GC, search latency, and concurrency.
11. Keep fielddata only if semantics require token-level operations and memory budget suffices.
12. Add integration tests to prevent query regressions.

Do not start by increasing heap or breaker limits. First determine which field representation the query is using and whether it can move to keyword.

## 22. Quick reference table

| Symptom or need | How to handle |
|---|---|
| Sort on text reports fielddata disabled | Use keyword sub-field |
| Terms aggregation on text throws error | Aggregate on keyword field |
| Both full-text search and exact sort needed | Create text + keyword multi-field |
| Need to aggregate analyzed tokens | Consider controlled fielddata |
| Heap climbs when fielddata loads | Identify field/query, prefer keyword/doc values |
| Fielddata circuit breaker trips | Check fielddata size, heap, and concurrency |
| Old documents lack keyword sub-field | Update by query or reindex |
| Mapping field type needs changing | Create new index and reindex |
| High-cardinality aggregation | Filter, cap buckets, or composite aggregation |
| Identify active fielddata usage | _cat/fielddata and node stats |
| Inspect breakers | _nodes/stats/breaker |
| Clear cache | Use intentionally only; does not change mappings |
| Spring Data mapping | @MultiField, @InnerField, @Field |
| Check real mapping | GET index/_mapping |
| Test queries | Integration tests with Elasticsearch |

Sorting and aggregation errors on text usually stem from queries targeting a field designed for full-text search. Keep text for match queries and create keyword multi-fields for exact filters, sorts, and terms aggregations. Fielddata can enable operations on analyzed tokens, yet it loads into heap, can create GC pressure, and can trip circuit breakers; enable it only when the use case truly requires it and memory has been measured. When adding a multi-field, old data does not automatically gain the new representation, so backfill via update by query or reindex. In Spring Data Elasticsearch, declare mappings with annotations or IndexOperations, use the right field paths in queries, and inspect actual mappings, fielddata stats, and breaker metrics before modifying memory settings.
