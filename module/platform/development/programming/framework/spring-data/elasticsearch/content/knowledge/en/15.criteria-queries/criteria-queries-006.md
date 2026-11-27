# Distinguishing Generated Query Context vs. Filter Context

Spring Data Elasticsearch's `CriteriaQuery` lets you describe search conditions with `Criteria` objects and translate them into Elasticsearch queries. When inspecting the generated output, it is important to distinguish two concepts:

- **Query context**: Elasticsearch checks whether a document matches and calculates a relevance score to rank results.
- **Filter context**: Elasticsearch only checks whether a document satisfies the condition; the condition does not contribute to the relevance score and may be cached when appropriate.

A business-level filtering condition does not automatically imply filter context. For example, `Criteria.where("status").is("ACTIVE")` looks like a status filter, yet the `Criteria` API places `is()` into query criteria entries. To understand the actual request generated, you must look at the operation type Spring Data uses and the final Query DSL structure.

## 1. Query Context and Filter Context in Elasticsearch

Elasticsearch evaluates conditions in two ways within Query DSL:

| Context | Purpose | Relevance score | Common examples |
| --- | --- | --- | --- |
| Query context | Find matching documents and evaluate how well each document matches the query content. | Can contribute to `_score`. | `match`, `multi_match`, `match_phrase`, `fuzzy`. |
| Filter context | Include or exclude documents based on a true/false condition. | Does not score from that condition. | Status conditions, price ranges, date ranges, or geo bounds when only narrowing the result set. |

For example, a user searches for products using the phrase `wireless keyboard` and wants to see only active products priced between 100 and 500:

- Product name needs text analysis and relevance ranking by match quality: query context.
- Status must equal `ACTIVE`: filter context is appropriate when the condition only narrows results.
- Price must be within range: filter context is appropriate if price does not need to influence relevance scoring.

In Elasticsearch, a `bool` query combines clauses by role:

| Clause | Behavior | Context |
| --- | --- | --- |
| `must` | Document must match the condition. | Query context; clause score is calculated. |
| `should` | Optional condition or relevance-boosting condition, depending on `minimum_should_match` and other clauses. | Query context. |
| `filter` | Document must satisfy the condition. | Filter context; no scoring. |
| `must_not` | Document must not satisfy the condition. | Filter context; no scoring. |

Query DSL example:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lte": 500
            }
          }
        }
      ]
    }
  }
}
~~~

Results are still ranked by the product name search. The status and price conditions simply restrict eligible documents.

## 2. `Criteria` Stores Two Separate Entry Groups

In Spring Data Elasticsearch, `Criteria` is a fluent API for creating conditions. A `Criteria` maintains two internal entry collections:

- `queryCriteriaEntries`: operations created for query context.
- `filterCriteriaEntries`: operations created for filter context.

When `CriteriaQuery` executes, Spring Data translates these entries into the query and filter portions of the Elasticsearch request. The `Criteria` API documentation clearly describes these two entry groups; do not guess the context solely from method names or business meaning.

### 2.1. Common Operations Added to Query Criteria

The following methods create a query criteria entry in the Spring Data Elasticsearch API:

| `Criteria` method | Meaning | Typical generated query |
| --- | --- | --- |
| `is(value)` | Equality match on value. | `term` query. |
| `in(values)` | Matches one of the values. | `terms` query. |
| `notIn(values)` | Does not match listed values. | Corresponding negated form. |
| `matches(text)` | Text search; tokens combined with OR. | `match` query with OR operator. |
| `matchesAll(text)` | Text search; tokens combined with AND. | `match` query with AND operator. |
| `between(a, b)` | Within range. | `range` query. |
| `greaterThan(value)` / `lessThan(value)` | Greater than / less than comparisons. | `range` query. |
| `exists()` | Field exists. | `exists` query. |
| `startsWith(value)` | Starts with string. | `prefix` query. |
| `contains(value)` / `endsWith(value)` | Contains or ends with string. | Typically creates a wildcard query. |
| `fuzzy(value)` | Approximate match. | `fuzzy` query. |

Key point: `is("ACTIVE")`, `in("ACTIVE", "PENDING")`, and `between(100, 500)` are familiar business filtering conditions, yet per the `Criteria` API they are still added to `queryCriteriaEntries`. If placed in query context, they can participate in `_score` calculation alongside other query clauses.

For strings needing exact matching, use a `keyword` field mapping. `in()` generates a terms query; the API documentation advises against using this operation on `text` fields transformed by an analyzer.

### 2.2. Operations That Create Filter Criteria Entries

Certain specialized operations create a filter criteria entry instead of a query criteria entry, notably geographic and parent/child relationship conditions:

| `Criteria` method | Meaning |
| --- | --- |
| `within(GeoPoint, distance)` | Point lies within a geographic radius around coordinates. |
| `within(GeoJson)` | Geometry lies inside the specified area. |
| `boundedBy(...)` | Point lies inside a bounding box. |
| `intersects(GeoJson)` | Geometry intersects the specified area. |
| `contains(GeoJson)` | Geometry contains the specified area. |
| `isDisjoint(GeoJson)` | Geometry does not intersect the specified area. |
| `hasChild(query)` | Child document relationship condition. |
| `hasParent(query)` | Parent document relationship condition. |

These methods have overloads for different coordinate and geometry types. Choose the data type matching your field mapping, such as `geo_point` or `geo_shape`.

Not all methods sharing the same name operate in the same context. For example, `contains(String)` creates a string-search query criteria entry, whereas `contains(GeoJson)` creates a geographic filter criteria entry.

## 3. Distinguishing AND/OR from Query/Filter Context

These are two independent concepts that are easy to confuse:

- `and()` and `or()` determine the logical relationship combining conditions.
- Query context and filter context determine how Elasticsearch evaluates each condition.

In `CriteriaQuery`, `AND` translates to a `must` relationship, while `OR` translates to a `should` relationship. Example:

~~~java
Criteria criteria = Criteria.where("lastName").is("Miller")
        .and("firstName").is("James");

Query query = new CriteriaQuery(criteria);
~~~

These are two conditions combined with AND. Because `is()` creates query criteria entries, these conditions belong to query context per the `Criteria` API.

OR example:

~~~java
Criteria firstName = Criteria.where("firstName").is("John")
        .or("firstName").is("Jack");

Query query = new CriteriaQuery(firstName);
~~~

The conditions for first name John or Jack are combined with `should`. Using OR does not automatically turn them into filter context.

You can use subcriteria to group more complex logic:

~~~java
Criteria firstNameIsJohnOrJack = new Criteria()
        .or("firstName").is("John")
        .or("firstName").is("Jack");

Criteria criteria = Criteria.where("lastName").is("Miller")
        .subCriteria(firstNameIsJohnOrJack);

Query query = new CriteriaQuery(criteria);
~~~

The logical meaning is `lastName = Miller AND (firstName = John OR firstName = Jack)`. Subcriteria controls condition grouping; it is not an operation that converts a query entry into a filter entry.

## 4. CriteriaQuery Example Generating Both Query and Filter Entries

Suppose a product document has these fields:

| Field | Mapping | Purpose |
| --- | --- | --- |
| `name` | `text` | Full-text search. |
| `status` | `keyword` | Product status. |
| `price` | `long` | Price range. |
| `location` | `geo_point` | Warehouse or store location. |

Illustrative entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Long)
    private Long price;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // Constructor, getters and setters
}
~~~

Creating Criteria:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.Criteria;

Criteria criteria = Criteria.where("name").matches("wireless keyboard")
        .and("status").is("ACTIVE")
        .and("price").between(100, 500)
        .and(new Criteria("location")
                .within(new GeoPoint(10.7769, 106.7009), "5km"));

Query query = new CriteriaQuery(criteria);
~~~

In this example:

- `matches("wireless keyboard")` is a query criteria entry for content search.
- `is("ACTIVE")` is a query criteria entry per the `Criteria` API, even though in business terms it filters status.
- `between(100, 500)` is a query criteria entry per the `Criteria` API.
- `within(GeoPoint, "5km")` is a filter criteria entry.

Spring Data combines the conditions with AND while preserving the distinction between query entries and filter entries. The query part can produce relevance scores; the filter part only restricts documents satisfying the geographic condition.

Executing the query via `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

public SearchHits<ProductDocument> searchNearbyProducts(
        ElasticsearchOperations operations) {

    Criteria criteria = Criteria.where("name").matches("wireless keyboard")
            .and("status").is("ACTIVE")
            .and("price").between(100, 500)
            .and(new Criteria("location")
                    .within(new GeoPoint(10.7769, 106.7009), "5km"));

    Query query = new CriteriaQuery(criteria);
    return operations.search(query, ProductDocument.class);
}
~~~

The returned results are products matching name, status, price range, and location. If you want status and price to be evaluated strictly in filter context, choose an API/Query DSL that lets you specify filters explicitly rather than assuming every business condition in Criteria automatically becomes a filter.

## 5. When Should You Use CriteriaQuery?

`CriteriaQuery` fits when you want to build queries step by step in Java without directly writing the entire Elasticsearch Query DSL.

Examples of suitable scenarios:

- Search filters assembled from form selections.
- Simple or moderate search conditions expressible using existing `Criteria` operations.
- Queries with multiple AND/OR conditions and supported geographic criteria.

Advantages:

- Easy to construct conditional criteria in Java code.
- Can compose Criteria step by step.
- Uses domain type mapping metadata during conversion.
- Avoids writing raw JSON Query DSL for common operations.

Limitations:

- Not every Query DSL feature has a corresponding `Criteria` operation.
- Do not assume `is`, `in`, and `between` conditions generate filter context.
- Complex queries involving `bool`, nested, aggregations, scripts, scoring, or filter composition may require `NativeQuery`.

## 6. Putting Business Conditions into Filter Context with NativeQuery

When you want text conditions to participate in scoring while status and price range conditions only restrict the result set, express them directly with `bool.must` and `bool.filter` in `NativeQuery`.

Example with Spring Data Elasticsearch 5.x/6.x and the Elasticsearch Java API Client:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("name")
                        .query("wireless keyboard")))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))))
                .filter(f -> f.range(r -> r.number(n -> n
                        .field("price")
                        .gte(100.0)
                        .lte(500.0))))
        ))
        .build();

SearchHits<ProductDocument> hits =
        operations.search(query, ProductDocument.class);
~~~

In the corresponding Query DSL, the main structure looks like:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 100,
              "lte": 500
            }
          }
        }
      ]
    }
  }
}
~~~

This clearly states the intent:

- `must` searches content and contributes to relevance score.
- `filter` checks status and price without contributing to score.

`NativeQuery` lets you use the Elasticsearch Java API Client query builders, making it appropriate when the Criteria API cannot express the required structure. Specific builder APIs may vary across client versions; use dependencies compatible with your project's Spring Data Elasticsearch version.

## 7. Distinguishing `bool.filter` and `post_filter`

In addition to `bool.filter`, Elasticsearch provides `post_filter` at the search request level. Both mechanisms filter returned results, yet there is a critical difference when using aggregations.

| Mechanism | Affects returned documents | Affects aggregations |
| --- | --- | --- |
| `bool.filter` inside `query` | Yes. | Yes; aggregations are computed on the document set after query/filter. |
| `post_filter` at search request level | Yes. | No; aggregations are computed before post-filter. |

For example, an e-commerce page displays a color filter alongside product counts per color:

- If the selected color is inside `bool.filter`, color aggregations are computed only over results already restricted by that color.
- If the selected color is in `post_filter`, the hit list is filtered by color while aggregations can still show counts for the other colors in the initial result set.

Thus, `post_filter` is useful for faceted search UIs that want to keep aggregations independent of the active filter. If you expect aggregations to obey the same condition, place the condition inside `bool.filter` within the query.

Spring Data provides filter APIs on some Query/NativeQuery types, and their exact mapping depends on the version. Do not just look at the name `withFilter` and assume it equates to `bool.filter`. When aggregations matter, verify whether the condition lands in `query.bool.filter` or `post_filter` in the actual request.

## 8. Impact of Filter Context on Score and Performance

### 8.1. Score

Query context can affect `_score`. When multiple clauses are in `bool.must` or `bool.should`, their scores are combined according to Elasticsearch's scoring rules.

Filter context contributes no score. Documents satisfying a filter can still receive scores from the query context portion; if a query contains only filters and no scoring query, Elasticsearch may assign the same default score to matching documents.

This matters when sorting by `_score`: keep content-matching conditions in query context and move constraints unrelated to relevance into filter context.

### 8.2. Caching and Processing Cost

Filter context avoids computing relevance scores for that condition. Elasticsearch can cache eligible filter results, especially for repeated and stable conditions. Not every filter is automatically cached in all situations; caching depends on query type, data, configuration, and Elasticsearch's internal heuristics.

Do not push every condition into filter solely under the assumption that filters are always faster. Choose context based on condition semantics:

- Condition needs to evaluate relevance: query context.
- Condition only needs true/false to narrow results: filter context.
- Whether the condition should affect aggregations: decide between `bool.filter` and `post_filter`.

## 9. How Mapping Affects Criteria Query Generation

Criteria operations are converted into Query DSL, yet whether results are accurate still depends on field mappings.

| Field to query | Recommended mapping | Suitable operations |
| --- | --- | --- |
| Name or description searched by words | `text` | `matches`, `matchesAll`, or equivalent full-text queries. |
| Status, code, or product type needing exact match | `keyword` | `is`, `in`. |
| Price, quantity, or score | `integer`, `long`, `float`, `double` | `between`, `greaterThan`, `lessThan`. |
| Creation or update date | `date` | `between`, `greaterThan`, `lessThan`. |
| Coordinates | `geo_point` | `within`, `boundedBy`. |
| Geometric area | `geo_shape` | `within`, `intersects`, `contains`, `isDisjoint` depending on mapping and operation. |

For example, `in("ACTIVE", "PENDING")` creates a terms query. If the field is `text`, an analyzer can alter tokens and cause results to differ from exact-match expectations. For status, use `keyword`.

`matches("wireless keyboard")` suits a `text` field, because Elasticsearch analyzes content with the analyzer. Using `matches` on a `keyword` field generally will not produce the full-text search behavior the query author expects.

## 10. How to Inspect the Actual Generated Conditions

Do not deduce the entire Query DSL solely from the Java snippet. When you need to confirm query/filter context, inspect the request sent to Elasticsearch.

Verification steps:

1. Enable appropriate logging for your version's client/transport in a development environment.
2. Run a CriteriaQuery with sample data that yields easily recognizable results.
3. Note `query`, `bool.must`, `bool.should`, `bool.filter`, and `post_filter` if present.
4. Compare result `_score` values when conditions are in query context versus filter context.
5. If aggregations exist, check whether the aggregations are constrained by the filter.
6. Disable detailed request logging after inspection, especially if queries contain user data or sensitive information.

You can use the Elasticsearch Profile API to analyze per-query cost when deep optimization is needed. Profiling incurs overhead and should be used in testing environments rather than enabled by default for all production requests.

## 11. Common Mistakes

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Status condition changes `_score` | `Criteria.is()` is generated as a query criteria entry. | Use NativeQuery with `bool.filter` if status only needs to narrow results. |
| `in()` fails to match strings | Field is `text` and the analyzer altered values. | Use `keyword` mapping for codes/statuses requiring exact match. |
| Geo condition does not appear in main query section | Geo operations create a separate filter criteria entry. | Inspect the filter section of the generated request and geo field mapping. |
| OR returns too many documents | `should` can be optional alongside `must`/`filter`, depending on `minimum_should_match`. | Define OR groups explicitly and set `minimum_should_match` if at least one branch must match. |
| Aggregation ignores the active filter | Condition was placed in `post_filter`. | Move the condition into `bool.filter` if aggregations should also be scoped. |
| Filter does not noticeably speed up results | Filter caching is not guaranteed and performance depends on query, data, shards, and cache. | Measure with real data; avoid assuming every filter is cached. |
| Criteria API cannot express the required query | Operation or Query DSL structure is not directly supported. | Use NativeQuery or StringQuery for the complex query portion. |

## 12. Choosing CriteriaQuery or NativeQuery?

| Need | Appropriate approach |
| --- | --- |
| Simple conditions, fluent API, clear AND/OR | `CriteriaQuery`. |
| Full-text search combined with supported Criteria predicates | `CriteriaQuery`, verify generated query/filter entries. |
| Status/range conditions that must sit in `bool.filter` | `NativeQuery` with `bool.filter`. |
| Complex queries with nested bools, scripts, function score, or multi-level queries | `NativeQuery`. |
| Aggregations with control over how filters affect aggregations | `NativeQuery` with an explicitly designed query/filter structure. |
| Pre-existing JSON Query DSL | `StringQuery` or `NativeQuery`. |

Spring Data `ElasticsearchOperations` works with all three Query types: `CriteriaQuery`, `StringQuery`, and `NativeQuery`. Choose the API that communicates intent clearly and makes inspecting the final request straightforward.

## 13. Workflow for Designing Query Conditions

When constructing queries, follow this order:

1. Identify which conditions must affect relevance scores, such as searching names or descriptions by content.
2. Identify which conditions only narrow documents, such as status, tenant, time range, or price range.
3. Verify mapping: `text` for full-text, `keyword` for exact match, numeric/date types for ranges, and geo types for locations.
4. If using CriteriaQuery, check whether operations are added to `queryCriteriaEntries` or `filterCriteriaEntries`.
5. Remember that `and()`/`or()` only control logical combination; they do not automatically convert a query entry into a filter entry.
6. If you need filter-context control for ordinary business fields, use NativeQuery with `bool.filter`.
7. If aggregations are present, decide whether filters should constrain aggregations or only filter hits via `post_filter`.
8. Observe actual requests and test on sample data before optimizing.

`CriteriaQuery` provides a Java way to build conditions, yet query context and filter context are separate concepts in Elasticsearch. Common operations like `is`, `in`, `between`, and `matches` are recorded by the Criteria API as query entries; some geo and parent/child operations create filter entries. When business predicates such as status or price must not affect scoring, express them in `bool.filter` via NativeQuery and verify how filters interact with aggregations.

## References

- [Spring Data Elasticsearch — Elasticsearch Operations and CriteriaQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Criteria API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Criteria.html)
- [Spring Data Elasticsearch — NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Elasticsearch — Query and filter context](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-filter-context.html)
- [Elasticsearch — Bool query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html)
