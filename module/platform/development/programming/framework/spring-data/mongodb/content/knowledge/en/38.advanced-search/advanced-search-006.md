# `$search`, `$searchMeta`, and Mapping Results to DTOs

## Objectives

In the **Advanced Search** chapter of `SPRING_DATA_MONGODB`, after learning how to connect and map documents with Spring Data MongoDB, we build an article search API featuring **relevance ranking**, **filtering**, **total result counts**, and **DTO outputs**. MongoDB Search provides two primary aggregation stages:

- `$search`: returns documents matching the query along with metadata such as the `searchScore` relevance score.
- `$searchMeta`: returns query metadata, such as total result counts and facet buckets, **without returning the list of article documents**.

Both stages belong to **MongoDB Search** (formerly commonly called Atlas Search) and use a **dedicated Search index**. They differ from the `$text` operator on traditional text indexes and are not created by the `@TextIndexed` annotation. This capability is available on MongoDB Atlas and self-managed environments/versions supporting MongoDB Search; verify deployment compatibility before practicing.

By the end of this lesson, you will be able to create a Search index, run pipelines containing `$search` and `$searchMeta`, project `searchScore`, return Java records/DTOs via `MongoTemplate.aggregate()`, and evaluate pagination, consistency, and performance.

## 1. Preparing the Dataset and Search Index

Suppose a technical documentation application has an `articles` collection:

```javascript
db.articles.insertMany([
  {
    title: "Tìm kiếm với Spring Data MongoDB",
    summary: "Hướng dẫn tích hợp MongoTemplate và aggregation",
    category: "backend",
    published: true
  },
  {
    title: "Thiết kế MongoDB Search",
    summary: "Truy vấn text, chấm điểm, facet và metadata",
    category: "database",
    published: true
  },
  {
    title: "MongoDB aggregation patterns",
    summary: "Pipeline patterns for reporting and filtering",
    category: "database",
    published: true
  },
  {
    title: "Bản nháp: tìm kiếm nâng cao",
    summary: "Nội dung thử nghiệm chưa công khai",
    category: "backend",
    published: false
  }
]);
```

Create a **MongoDB Search index** named `article-search` (`mongosh` supports the Search index creation method):

```javascript
db.articles.createSearchIndex("article-search", {
  mappings: {
    dynamic: false,
    fields: {
      title: { type: "string" },
      summary: { type: "string" },
      category: { type: "token" },
      published: { type: "boolean" }
    }
  }
});
```

Mapping explanation:

| Field | Search Index Type | Usage |
| --- | --- | --- |
| `title` | `string` | Text search via `text` |
| `summary` | `string` | Text search via `text` |
| `category` | `token` | Intact categorical value, used for equality filtering or facets |
| `published` | `boolean` | Filter published articles with `equals` |

`dynamic: false` indexes only the listed fields. Querying an unindexed field or one indexed with the wrong type may produce unexpected results.

**Note on the dataset:** the example mixes Vietnamese and English to illustrate technical integration. The default analyzer does not guarantee Vietnamese word segmentation, accent-insensitive search, or Vietnamese synonyms like a search engine tuned for Vietnamese. For accurate Vietnamese search in production, design and evaluate an appropriate analyzer rather than assuming the example configuration handles every spelling variation.

Search index creation is **asynchronous**. You can monitor progress and status via the management UI or:

```javascript
db.articles.getSearchIndexes("article-search");
```

Wait until the index is queryable before running the pipelines in the following sections. `db.articles.getIndexes()` lists traditional MongoDB indexes; it does not replace `getSearchIndexes()`.

## 2. Using `$search` to Retrieve Results

A pipeline that returns only published articles, searching keywords in `title` and `summary`:

```javascript
db.articles.aggregate([
  {
    $search: {
      index: "article-search",
      compound: {
        must: [
          {
            text: {
              query: "MongoDB",
              path: ["title", "summary"]
            }
          }
        ],
        filter: [
          {
            equals: {
              path: "published",
              value: true
            }
          }
        ]
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 0,
      id: { $toString: "$_id" },
      title: 1,
      summary: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  }
]);
```

Processing flow:

1. `$search` runs the search against the `article-search` index. This stage **must be first in the pipeline** (including supported sub-pipelines).
2. `compound.must` requires documents to match the keyword clause. `compound.filter` keeps only records with `published = true`; filter narrows results without scoring relevance like a text clause.
3. `$limit` caps the number of documents before projection, avoiding loading the full result set into the application.
4. `$project` shapes the exact output returned to the frontend: omits the raw `_id`, produces a string `id`, selects display fields, and surfaces `searchScore` metadata as `score`.

Illustrative output (scores are examples only, not fixed values):

```json
[
  {
    "id": "673a11111111111111111111",
    "title": "Tìm kiếm với Spring Data MongoDB",
    "summary": "Hướng dẫn tích hợp MongoTemplate và aggregation",
    "category": "backend",
    "score": 2.18
  }
]
```

MongoDB Search sorts hits by **descending relevance score** by default when no other sort is specified. The score is computed from the query, analyzer, term statistics, and scoring config; it is neither a percentage nor a probability of correctness. When two documents tie on score, their relative order may be non-deterministic, which must be considered during pagination.

### Common Operators in `$search`

| Component | Meaning | Example |
| --- | --- | --- |
| `text` | Searches terms on indexed `string` fields | `text: {query: "mongo", path: "title"}` |
| `phrase` | Searches for a phrase in token sequence | `phrase: {query: "spring data", path: "title"}` |
| `autocomplete` | Supports typeahead word completion | Requires corresponding `autocomplete` mapping |
| `compound.must` | Mandatory conditions that must all match | Keywords + other required clauses |
| `compound.should` | Optional conditions that boost relevance when matched | Boost when `title` contains the keyword |
| `compound.filter` | Filtering conditions, do not contribute to score | `published = true` |
| `equals` | Exact equality match on compatible index types | `category` mapped as `token` |

Example adding a category filter to `filter`:

```javascript
filter: [
  { equals: { path: "published", value: true } },
  { equals: { path: "category", value: "backend" } }
]
```

To use `fuzzy` (tolerating minor typos) in `text`, you can add `fuzzy: { maxEdits: 1 }` to the `text` configuration where appropriate. Carefully evaluate edit thresholds, cost, and your actual vocabulary; do not enable fuzzy by default on every query.

## 3. Using `$searchMeta` for Total Counts and Facets

`$searchMeta` uses the same search operators but **returns metadata** rather than articles. Example counting the exact number of articles matching the keyword and filter:

```javascript
db.articles.aggregate([
  {
    $searchMeta: {
      index: "article-search",
      compound: {
        must: [
          { text: { query: "MongoDB", path: ["title", "summary"] } }
        ],
        filter: [
          { equals: { path: "published", value: true } }
        ]
      },
      count: { type: "total" }
    }
  }
]);
```

The output has the shape:

```json
[
  { "count": { "total": 3 } }
]
```

The number `3` only illustrates the structure, not a guaranteed hit count for the sample data. When running, read the value returned by MongoDB.

There are two common count types:

- `count: { type: "total" }` returns the **exact result count**, which can be slower on large queries.
- `count: { type: "lowerBound" }` returns a **lower bound** in `count.lowerBound`, suited for UIs that only need to know at least how many results exist; it must not be presented as an exact total.

**Do not read `count.lowerBound` and label it “Exact total”**. When relying on defaults or using lower bound, code must read the right field name and convey its approximate meaning.

### Facets: Grouping Counts by Category

When the UI needs category filter counts, `$searchMeta` can return buckets grouped by `category`. This field is already indexed as `token`:

```javascript
db.articles.aggregate([
  {
    $searchMeta: {
      index: "article-search",
      facet: {
        operator: {
          compound: {
            must: [
              { text: { query: "MongoDB", path: ["title", "summary"] } }
            ],
            filter: [
              { equals: { path: "published", value: true } }
            ]
          }
        },
        facets: {
          byCategory: {
            type: "string",
            path: "category",
            numBuckets: 10
          }
        }
      },
      count: { type: "total" }
    }
  }
]);
```

The returned metadata includes `facet.byCategory.buckets`, where each bucket contains `_id` and its `count`. If the frontend needs both total count and suggested categories, the API can map both `count` and `facet` into a dedicated metadata DTO. Note that facets count across all documents **matching the facet's search operator**, not necessarily the same set as additional filters applied later in the pipeline.

### Using `$search` and `$$SEARCH_META` in the Same Pipeline

If you want both hits and metadata from **a single query** in one pipeline, you can add `count` to `$search` and access the `$$SEARCH_META` variable in a subsequent supported stage:

```javascript
db.articles.aggregate([
  {
    $search: {
      index: "article-search",
      text: { query: "MongoDB", path: ["title", "summary"] },
      count: { type: "total" }
    }
  },
  { $limit: 10 },
  {
    $facet: {
      hits: [
        {
          $project: {
            _id: 0,
            id: { $toString: "$_id" },
            title: 1,
            score: { $meta: "searchScore" }
          }
        }
      ],
      metadata: [
        { $replaceWith: "$$SEARCH_META" },
        { $limit: 1 }
      ]
    }
  }
]);
```

This returns a single object containing `hits` and `metadata` arrays, avoiding manual combination of two queries in the application. Because this example uses a simple `text` query, its results **differ** from the `compound` example filtering `published`; in real usage, include the exact same filters inside `$search` so the API does not expose draft data. For systems prioritizing clarity in performance and DTO structure, keeping two pipelines as shown in the next section is a clean option.

## 4. Mapping `$search` Results to Java DTOs

### Why Use DTOs?

Documents in MongoDB may contain sensitive or internal fields that the UI does not need. DTOs define an output contract independent of the persisted entity. Example:

```java
import java.util.List;

public record ArticleHit(
    String id,
    String title,
    String summary,
    String category,
    Double score
) {}

public record ArticleSearchResult(
    List<ArticleHit> hits,
    long total,
    int page,
    int size
) {}
```

These are two separate Java records in the same package, each placed in its own `.java` file. With Java records, Spring Data MongoDB can map aggregation results to the constructor by field name.

In the Java pipeline, several mappings need to be explicit:

| MongoDB Source | Field Projection | DTO |
| --- | --- | --- |
| `_id` of type ObjectId | `id: {$toString: "$_id"}` | `String id` |
| `title` | `title: 1` | `String title` |
| `summary` | `summary: 1` | `String summary` |
| `category` | `category: 1` | `String category` |
| `{$meta: "searchScore"}` | `score` | `Double score` |

Do not expect `@TextScore` (meant for traditional text search) to automatically capture MongoDB Search metadata. In this example, `$project` explicitly surfaces `searchScore` as a regular field named `score`, which `MongoTemplate` then maps to the DTO.

### `MongoTemplate` Implementation: Fetching Hits and Total

The following example uses `org.bson.Document` to build MongoDB Search stages; this avoids injecting raw user input into a string-concatenated JSON snippet. Keep `$search` and `$searchMeta` as the **first stage** in each pipeline.

```java
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

@Service
public class ArticleSearchService {
    private static final String COLLECTION = "articles";
    private static final String SEARCH_INDEX = "article-search";

    private final MongoTemplate mongoTemplate;

    public ArticleSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public ArticleSearchResult search(String keyword, int page, int pageSize) {
        if (keyword == null || keyword.isBlank() || keyword.length() > 200) {
            throw new IllegalArgumentException("Keyword must be 1-200 characters");
        }
        if (page < 0) {
            throw new IllegalArgumentException("page must not be negative");
        }
        if (pageSize < 1 || pageSize > 50) {
            throw new IllegalArgumentException("pageSize must be between 1 and 50");
        }

        long skip = (long) page * pageSize;
        if (skip > 1000) {
            throw new IllegalArgumentException(
                "Deep pagination requires searchAfter"
            );
        }

        Document conditions = searchConditions(keyword.trim());

        AggregationOperation searchStage = context -> new Document(
            "$search",
            new Document("index", SEARCH_INDEX)
                .append("compound", conditions)
        );

        AggregationOperation skipStage =
            context -> new Document("$skip", skip);
        AggregationOperation limitStage =
            context -> new Document("$limit", pageSize);

        AggregationOperation projectStage = context -> new Document(
            "$project",
            new Document("_id", 0)
                .append("id", new Document("$toString", "$_id"))
                .append("title", 1)
                .append("summary", 1)
                .append("category", 1)
                .append("score", new Document("$meta", "searchScore"))
        );

        Aggregation hitsPipeline = Aggregation.newAggregation(
            searchStage, skipStage, limitStage, projectStage
        );

        List<ArticleHit> hits = mongoTemplate
            .aggregate(hitsPipeline, COLLECTION, ArticleHit.class)
            .getMappedResults();

        AggregationOperation metaStage = context -> new Document(
            "$searchMeta",
            new Document("index", SEARCH_INDEX)
                .append("compound", conditions)
                .append("count", new Document("type", "total"))
        );

        Document metadata = mongoTemplate.aggregate(
            Aggregation.newAggregation(metaStage),
            COLLECTION,
            Document.class
        ).getUniqueMappedResult();

        long total = 0;
        if (metadata != null) {
            Document count = metadata.get("count", Document.class);
            if (count != null && count.get("total") instanceof Number number) {
                total = number.longValue();
            }
        }

        return new ArticleSearchResult(hits, total, page, pageSize);
    }

    private Document searchConditions(String keyword) {
        Document text = new Document("query", keyword)
            .append("path", List.of("title", "summary"));

        Document published = new Document("path", "published")
            .append("value", true);

        return new Document("must", List.of(
            new Document("text", text)
        )).append("filter", List.of(
            new Document("equals", published)
        ));
    }
}
```

**Points to verify when reading the code:**

- `searchConditions()` centralizes the search criteria for both pipelines, ensuring `hits` and `total` obey the same filters.
- `AggregationOperation` lets you build stages that lack a dedicated DSL using `Document`, while Spring Data still handles execution and result mapping. In supported versions, `Aggregation.stage(...)` is also an option for custom BSON/JSON stages.
- `$search` comes first in the hits pipeline, followed by `$skip`, `$limit`, and `$project`. Capping `skip` prevents costly deep-offset pagination.
- `$searchMeta` comes first in the metadata pipeline, returning `count.total`. Reading it as `Number` accommodates different BSON numeric types returned by the driver.
- `id` is converted from `_id` to a string directly in the projection. If the system uses non-ObjectId/String IDs or if IDs can be `null`, adjust the conversion accordingly.
- The two pipelines execute as **two separate aggregation commands**. If data or the Search index changes between commands, `total` and `hits` may briefly diverge; define what consistency level is acceptable for the UI.

A REST controller can return the DTO directly:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/articles")
public class ArticleSearchController {
    private final ArticleSearchService service;

    public ArticleSearchController(ArticleSearchService service) {
        this.service = service;
    }

    @GetMapping("/search")
    public ArticleSearchResult search(
        @RequestParam String q,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "10") int size
    ) {
        return service.search(q, page, size);
    }
}
```

Example request: `GET /api/articles/search?q=mongodb&page=0&size=10`. This controller focuses on demonstrating the search flow; a production application needs proper HTTP error handling for `IllegalArgumentException`, user-level access control, and latency monitoring.

## 5. When to Use Repository `@Aggregation`?

If a pipeline is fixed and only needs parameters like keyword or limit, Spring Data MongoDB allows `@Aggregation` on a repository:

```java
import java.util.List;

import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ArticleRepository
        extends MongoRepository<ArticleDocument, String> {

    @Aggregation(pipeline = {
        "{ $search: { " +
            "index: 'article-search', " +
            "text: { query: ?0, path: ['title', 'summary'] } " +
          "} }",
        "{ $limit: ?1 }",
        "{ $project: { " +
            "_id: 0, id: { $toString: '$_id' }, " +
            "title: 1, summary: 1, category: 1, " +
            "score: { $meta: 'searchScore' } " +
          "} }"
    })
    List<ArticleHit> searchByText(String keyword, int limit);
}
```

In this example, `ArticleDocument` is an entity annotated with `@Document(collection = "articles")`, `@Id String id`, and the corresponding fields. This illustrates a **fixed pipeline**; to match the API in section 4, add a `compound.filter` for `published = true` and the same `$searchMeta` counting flow. Do not copy this method into a public API if drafts must be hidden without adding the filter.

Choose `MongoTemplate` when there are optional conditions, pagination, and complex metadata; choose `@Aggregation` when the pipeline is short, rarely changes, and maps cleanly. Either way, verify that the DTO maps the exact field names output by `$project`.

## 6. Verifying Results and Diagnosing Errors

A verification workflow can follow these steps:

1. Ensure the deployment supports MongoDB Search, and that the `article-search` Search index exists on the right collection and is ready.
2. Run `$search` in `mongosh`, inspecting the document hits and scores.
3. Run `$searchMeta` with the **exact same query and filter**; record `count.total` or `count.lowerBound` as requested.
4. Call the Spring API, checking that `id` is a string, `score` is numeric, and no fields outside the DTO are exposed.
5. Insert a document with `published: false` containing the keyword and verify it neither appears in hits nor counts toward total.
6. Test blank queries, negative pages, oversized page sizes, zero-result queries, and tied scores.
7. Measure execution time on realistically sized data; never draw conclusions from just a few sample documents.

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `$search` fails on local MongoDB | Deployment does not support MongoDB Search | Check platform and version; deploy an appropriate Search service |
| Search index not found | Wrong name or index not yet ready | Check `getSearchIndexes()`, collection name, and index status |
| Invalid pipeline order | `$match` or `$project` placed before `$search` | Move `$search` or `$searchMeta` to the start of the pipeline |
| Keyword query returns no hits | Field not indexed as `string` or unsuitable analyzer | Inspect mappings and sample data |
| `category` filter behaves unexpectedly | `category` not indexed as `token` for `equals` | Fix the mapping and wait for the index to update |
| DTO missing `id` or `score` | Missing `$toString`, missing `$meta`, or wrong alias | Inspect `$project` output before DTO mapping |
| `total = 0` despite having hits | Code reads `total` while query returns `lowerBound`, or filters differ | Align metadata structure and share filter conditions |
| `total` and `hits` occasionally differ | Two separate aggregations; Search index updates asynchronously | Accept the lag or use a combined metadata strategy |
| Pagination slows down on high pages | `$skip` over large hit sets | Use reference-based `searchAfter` pagination where available and design a deterministic sort |

### Performance, Consistency, and Safety

**Limits and ordering:** Use `$limit` when returning hits, and consider `$search` with sorting/scoring and `searchAfter` for deep pages instead of unbounded `$skip`. When consistent pagination is required, design a tie-breaker for equal scores and check how sorting and pagination tokens are supported in your MongoDB Search version.

**Counts:** `total` can be resource-intensive on large hit sets; `lowerBound` is better suited when the UI only needs “at least N results”. To analyze scoring, enable `scoreDetails: true` in `$search` and project `searchScoreDetails` metadata, but restrict this to diagnostics since it increases payload size.

**Sensitive data:** Return only the fields the client needs via `$project` and DTOs. Enforce access-control conditions inside the Search query itself; never fetch all hits and filter confidential records in the application after pagination. Account for Search index sync lag relative to the source collection if business rules require immediate permission revocation.

**Observability:** Measure search latency, count latency, keyword/size distributions, zero-hit rates, and Search index errors. Track index size and update speed as data grows. For Vietnamese search problems, build a benchmark query set to evaluate precision/recall, word segmentation, diacritics, synonyms, and performance on representative data.

## 7. Practice Exercises

**Exercise 1 — Search hits:** Create a Search index for `articles` with `title`, `summary`, `category`, and `published`. Write a `$search` pipeline using `text` and `compound.filter`. Project results into a DTO with a string `id` and `score` taken from `searchScore`.

**Exercise 2 — Total and lower bound:** Run `$searchMeta` with `count.total` and `count.lowerBound` on the same keyword. Observe the different JSON structures and explain why a lower bound must not be displayed as an exact count.

**Exercise 3 — Facets:** Use `$searchMeta.facet` to return `category` buckets. Add a category filter and verify that facets, hits, and total share the same business criteria.

**Exercise 4 — DTO and API:** Implement `ArticleSearchService` and `GET /api/articles/search`. Verify `_id -> id` mapping, `$meta -> score`, max page size, empty keywords, and `published = false` articles.

**Exercise 5 — Operations:** Compare separate `$search`/`$searchMeta` pipelines against a combined `$search` + `$$SEARCH_META` pipeline. Analyze query count, latency, consistency, and DTO complexity, then choose the right approach for a UI displaying total result counts.

**Completion criteria:** Can create and verify a Search index; explain the difference between `$search` and `$searchMeta`; write pipelines with scoring and counts; map results properly to Spring Data MongoDB DTOs; and recognize risks around pagination, data filtering, and asynchronous Search index updates.

## References

- [MongoDB Search — $search aggregation stage](https://www.mongodb.com/docs/search/query/aggregation-stages/search/)
- [MongoDB Search — $searchMeta aggregation stage](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/)
- [MongoDB Search — Count MongoDB Search Results](https://www.mongodb.com/docs/search/query/counting/)
- [MongoDB Search — facet operator](https://www.mongodb.com/docs/search/query/operators-collectors/facet/)
- [MongoDB Search — Create a Search Index](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/)
- [MongoDB Search — Query Reference](https://www.mongodb.com/docs/search/query/query-ref/)
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — Aggregation Repository Annotation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)
