# Search Index, Analyzers, and Deployment Environment Requirements

> **Scope:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and interact with MongoDB via `MongoTemplate` or repositories; practicing queries, aggregation, indexes, testing, and performance diagnostics. This lesson belongs to the **Advanced Search** chapter, focusing on MongoDB Search (formerly commonly known as Atlas Search), how text is analyzed, and the requirements to deploy this feature.

## 1. Objectives and Real-World Scenario

After this lesson, readers will be able to:

1. Distinguish a **Search index** from B-tree indexes, standard `text` indexes, and Vector Search indexes.
2. Design `mappings` for searchable fields; choose an `analyzer` for index time and a `searchAnalyzer` for query time.
3. Create, check the status of, and use a Search index with `$search` or `$searchMeta`.
4. Execute search pipelines using `MongoTemplate`, validate input data, and handle results with relevance scores.
5. Verify Atlas or self-managed environment requirements before depending on Search in an application.

**Running example:** A store needs to search products by Vietnamese name and description, filtering by category, availability, and price range. Users might type “bàn phím”, “BÀN PHÍM”, or similar phrases. A simple `findByNameContaining` query cannot easily handle word analysis, relevance ranking, and compound filters all at once.

## 2. What Is a Search Index and How Does It Differ from Other Indexes?

MongoDB Search uses a specialized index for search, organizing **terms/tokens** extracted from document content to serve keyword queries and relevance ranking. Search indexes are managed separately from a collection's regular indexes.

| Mechanism | When to Use | Key Differences |
| --- | --- | --- |
| B-tree index created by `createIndex` or `@Indexed` | Equality filtering, range comparisons, field sorting | Does not provide a language analysis pipeline or full-text search scoring |
| MongoDB text index (`createIndex({name: "text"})`, `@TextIndexed`) | Basic full-text keyword search via `$text` | Different API and configuration capabilities from MongoDB Search; cannot be used for `$search` |
| **MongoDB Search index** (`search` type) | Full-text, fuzzy, phrase, autocomplete, highlight, facet, relevance | Uses `$search` / `$searchMeta`; requires a Search-supported environment |
| Vector Search index (`vectorSearch` type) | Finding similar documents via embeddings | Uses `$vectorSearch` and dedicated vector config; does not replace keyword Search indexes |

**Key takeaway:** Creating a text index with `@TextIndexed` does not make `$search` work. Likewise, calling `mongoTemplate.indexOps(...)` to create a B-tree index does not create a Search index.

### Three Parts of a Search Index

- **Index definition:** name, `mappings`, and related options.
- **Field mapping:** data paths and search types (`string`, `token`, `number`, `boolean`, `date`, `autocomplete`, ...), enabling the corresponding operators.
- **Analyzer:** rules for converting text into tokens at index time and at query time.

The processing flow can be visualized as:

```text
Document in collection
    └─> per-field mapping ──> analyzer ──> tokens in Search index
                                                    │
User enters query ──> searchAnalyzer ──> tokens ────┘
                                                    ↓
                                        $search: match and score
                                                    ↓
                                      $project / $limit / DTO
```

## 3. Designing Mappings: Dynamic or Static?

A minimal definition can enable dynamic mapping:

```javascript
db.products.createSearchIndex("products_dynamic", {
  mappings: { dynamic: true }
});
```

When `dynamic: true`, Search automatically maps indexable field types. This is convenient for experimentation, but it can index fields that do not serve queries, increasing size, resource usage, and the risk of behavior changes as the document schema evolves.

In real applications, you usually start with `dynamic: false` and list the fields to search:

```javascript
{
  mappings: {
    dynamic: false,
    fields: {
      name: { type: "string" },
      description: { type: "string" },
      category: { type: "token" },
      price: { type: "number" },
      available: { type: "boolean" }
    }
  }
}
```

Meaning of the choices:

- `string` suits full-text search by tokens and relevance.
- `token` suits categorical values needing exact matching, such as group codes or tenant IDs.
- `number` and `date` support filtering or range queries when supported by the operator.
- `boolean` supports true/false filter conditions.
- `autocomplete` is for typeahead suggestions, using its own configuration and operator.

`dynamic: false` keeps the search schema controlled. Renaming a field in a document or in `@Field` annotations can cause queries to no longer match the indexed path; both the index definition and the `$search` query must be re-evaluated.

## 4. How Do Analyzers Work?

An **analyzer** turns strings into matchable tokens. For a custom analyzer, the process typically consists of:

1. `charFilters` (optional): transforms input text before tokenization.
2. `tokenizer`: splits text into tokens, e.g., on word boundaries.
3. `tokenFilters` (optional): lowercasing, stop-word removal, stemming, diacritic folding, or n-gram generation.

Simple example: “Bàn Phím Cơ” can be split into word tokens and converted to lowercase. Tokenization rules depend on the tokenizer; **the standard tokenizer is not a semantic Vietnamese word segmenter**, so do not expect it to automatically understand all multi-syllable compound words.

### `analyzer` and `searchAnalyzer`

- `analyzer` runs when indexing data from documents.
- `searchAnalyzer` runs when processing query text, especially for the `text` operator.
- If `searchAnalyzer` is omitted, Search usually uses the field's `analyzer`; if both are omitted, it uses the default standard analyzer.

Both sides must produce compatible tokens. For instance, if the index folds diacritics while the query preserves them under a conflicting rule, recall can drop. Conversely, an analyzer that splits into too many tokens often produces noisy results.

| Analyzer / Technique | Best For | Notes |
| --- | --- | --- |
| Standard (`lucene.standard`) | General word search | Does not automatically handle all Vietnamese language needs |
| Keyword (`lucene.keyword`) | Entire string as a single token | Not suitable for matching individual words in long text |
| Lowercase | Case-insensitive matching | Configured as a token filter in a custom analyzer |
| `asciiFolding` or `icuFolding` | Attempting diacritic/Unicode normalization | Test against Vietnamese datasets, especially special characters and diacritics |
| N-gram, edge-gram, or `autocomplete` mapping | Prefix/substring suggestions | Has specific index overhead and quality trade-offs; not identical to full-text search |

### Custom Analyzer Example for Vietnamese

A practical approach is using the `standard` tokenizer, lowercasing, and testing `asciiFolding`. In the following example, `originalTokens: "include"` keeps the original token alongside the folded version (where applicable):

```javascript
{
  analyzers: [
    {
      name: "vi_fold",
      tokenizer: { type: "standard" },
      tokenFilters: [
        { type: "lowercase" },
        { type: "asciiFolding", originalTokens: "include" }
      ]
    }
  ],
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      },
      description: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      }
    }
  }
}
```

This is an **illustrative configuration**, not a guarantee that unaccented Vietnamese search will always achieve desired quality. You need to inspect tokens and actual results for pairs like “bàn/ban”, “điện/dien”, “máy/may”, accented brand names, and multi-syllable phrases. When deep Vietnamese word segmentation is required, evaluate dedicated language-processing options and the analyzer capabilities supported by your environment.

## 5. Complete Example in `mongosh`

The following commands must be run in an environment that supports MongoDB Search, using an account with permission to create Search indexes. Select the practice database:

```javascript
use shop_demo

db.products.insertMany([
  {
    _id: 1,
    name: "Bàn phím cơ không dây",
    description: "Bàn phím gõ êm cho văn phòng",
    category: "keyboard",
    price: 1250000,
    available: true
  },
  {
    _id: 2,
    name: "Chuột không dây",
    description: "Chuột dùng cho văn phòng",
    category: "mouse",
    price: 550000,
    available: true
  },
  {
    _id: 3,
    name: "Bàn phím cơ có dây",
    description: "Bàn phím cho gaming",
    category: "keyboard",
    price: 890000,
    available: false
  }
]);
```

Create a Search index named `products_text_v1`. The index name is chosen by the application; it does not depend on `_id` or a B-tree index name.

```javascript
db.products.createSearchIndex("products_text_v1", {
  analyzers: [
    {
      name: "vi_fold",
      tokenizer: { type: "standard" },
      tokenFilters: [
        { type: "lowercase" },
        { type: "asciiFolding", originalTokens: "include" }
      ]
    }
  ],
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      },
      description: {
        type: "string",
        analyzer: "vi_fold",
        searchAnalyzer: "vi_fold"
      },
      category: { type: "token" },
      price: { type: "number" },
      available: { type: "boolean" }
    }
  }
});
```

**Index creation is an asynchronous operation.** Returning from the command does not mean all data is immediately searchable. Check status:

```javascript
db.products.getSearchIndexes("products_text_v1");
```

Check `status` and `queryable` in the output. `READY` indicates the index can serve queries; `BUILDING` may not yet be queryable for a new index. `FAILED` requires checking configuration errors; `STALE` warns that the index may return outdated data. The standard `getIndexes()` command does not list Search indexes.

### Full-Text Search with Filter Conditions

```javascript
db.products.aggregate([
  {
    $search: {
      index: "products_text_v1",
      compound: {
        must: [
          {
            text: {
              query: "bàn phím",
              path: ["name", "description"]
            }
          }
        ],
        filter: [
          { equals: { path: "category", value: "keyboard" } },
          { equals: { path: "available", value: true } },
          { range: { path: "price", lte: 1500000 } }
        ]
      }
    }
  },
  {
    $project: {
      name: 1,
      description: 1,
      price: 1,
      category: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
]);
```

Explanation:

- `text` queries indexed text fields; `path` must match the field name stored in MongoDB.
- `compound.must` requires the search condition; `compound.filter` applies filter conditions without directly contributing to the relevance score.
- `score` reads from `searchScore` metadata to observe relevance ordering; this score is not a probability and has no fixed scale across different configurations.
- `$search` must appear first in the pipeline where it is used. Afterwards, `$project`, `$limit`, and other suitable aggregation stages can follow.

With the sample data, the goal is to return available keyboards priced at most 1,500,000. Actual results depend on the index being `READY` and how the analyzer generates tokens.

### When to Use `$searchMeta`?

`$searchMeta` returns metadata such as result counts or facets instead of the list of matching documents. For example, counting total products whose name contains the search term:

```javascript
db.products.aggregate([
  {
    $searchMeta: {
      index: "products_text_v1",
      text: { query: "bàn phím", path: "name" },
      count: { type: "total" }
    }
  }
]);
```

Consider the cost of exact counting on large datasets; in some cases `lowerBound` can be used instead. `$searchMeta` must also be the first stage in its pipeline.

### Typeahead Suggestions

If the requirement is suggesting names as the user types character by character, build a separate `autocomplete` index instead of expecting a full-text analyzer to handle this behavior:

```javascript
db.products.createSearchIndex("products_suggest_v1", {
  mappings: {
    dynamic: false,
    fields: {
      name: {
        type: "autocomplete",
        tokenization: "edgeGram",
        minGrams: 2,
        maxGrams: 15
      }
    }
  }
});

db.products.aggregate([
  {
    $search: {
      index: "products_suggest_v1",
      autocomplete: { path: "name", query: "bàn ph" }
    }
  },
  { $limit: 5 }
]);
```

With autocomplete, design diacritic handling, prefix lengths, and ranking according to user data. You can test multi-type mapping on the same field when needing to serve both `text` and `autocomplete`.

## 6. Calling Search with Spring Data MongoDB

`MongoTemplate` can execute aggregations containing a `$search` stage. Using `Document` lets the application pass MongoDB Search expressions when Spring Data's high-level API does not cover all needed operators.

The following example service builds a Search stage parameterized by user input, appends the relevance score, and limits the number of rows. It assumes the collection stores the exact field names `name`, `description`, and `available` as shown above.

```java
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final MongoTemplate mongoTemplate;

    public ProductSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> searchProducts(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return List.of();
        }

        String query = keyword.trim();

        Document text = new Document("text",
                new Document("query", query)
                        .append("path", List.of("name", "description")));

        Document available = new Document("equals",
                new Document("path", "available")
                        .append("value", true));

        Document compound = new Document("must", List.of(text))
                .append("filter", List.of(available));

        AggregationOperation searchStage = context ->
                new Document("$search",
                        new Document("index", "products_text_v1")
                                .append("compound", compound));

        AggregationOperation projectStage = context ->
                new Document("$project",
                        new Document("name", 1)
                                .append("description", 1)
                                .append("price", 1)
                                .append("score",
                                        new Document("$meta", "searchScore")));

        Aggregation pipeline = Aggregation.newAggregation(
                searchStage,
                projectStage,
                Aggregation.limit(10)
        );

        return mongoTemplate
                .aggregate(pipeline, "products", Document.class)
                .getMappedResults();
    }
}
```

**Integration notes:**

- `MongoTemplate` still goes through the MongoDB Java Driver and requires the right connection string, permissions, SSL/TLS, and a Search-supported environment.
- The `Document` snippet above represents **actual field names in the collection**. If the entity uses `@Field("product_name")`, update `path` and the projection accordingly; do not assume every string in a raw stage is remapped by Spring.
- Limit query string length, limit result counts, check user permissions, and strip sensitive fields before returning from the API. Never build JSON manually by concatenating strings from user input.
- To map to a DTO, you can use `AggregationResults<YourDto>` after confirming `_id` types and projected fields match the constructor/mapper.
- Depending on the version, Spring Data provides `SearchIndexOperations` to manage some Search index types. Check the API for your dependency version; defining full indexes via `mongosh` helps separate infrastructure management from data reads.
- `MongoRepository` works great for CRUD queries, but derived query methods such as `findByNameContaining` do not automatically turn into `$search` operators. Use a custom repository or a service with `MongoTemplate` when a Search pipeline is needed.

## 7. Support Requirements by Deployment Environment

**You cannot infer Search availability just from a successful MongoDB connection.** You must verify the deployment type, server version, Search service/process, and index management permissions.

| Environment | Can Use MongoDB Search? | Conditions to Verify |
| --- | --- | --- |
| MongoDB Atlas Free / Flex | Yes, for testing within each cluster tier's limits | Active cluster, Search index created, version and resources support the features used |
| MongoDB Atlas Dedicated | Yes, suited for larger operational workloads | Search index, resource sizing/cost, Search Nodes if used, permissions, and monitoring |
| Atlas local deployment | Yes, in local options provided by MongoDB | Use the official local distribution/config supporting Search; do not confuse with an arbitrary `mongod` process |
| MongoDB Community self-managed | Yes, in versions/deployments supporting MongoDB Search (introduced starting in 8.2) | Requires configuring the Search component (`mongot`), supported OS, and compatible version pairs; current docs require checking the compatibility matrix |
| MongoDB Enterprise self-managed | Yes, with officially documented topologies/versions, including Kubernetes orchestration | Requirements on MongoDB Server, `mongot`, operator, permissions, and topology; do not assume every Enterprise host has Search ready |
| Older MongoDB or local `mongod` without Search configured | Cannot use `$search` by default | Switch to a supported environment or consider `$text` / other queries depending on requirements |

**Regarding self-managed:** Search capability expanded to Community starting in the MongoDB 8.2 branch, but being **introduced in a version** is different from a version combination **still being on the current support list**. At the time of writing, MongoDB Search compatibility documentation specifies exact MongoDB Server and `mongot` pairs, requirements for newer releases, and platform limits. Before production deployment, check [Compatibility and Requirements for mongot](https://www.mongodb.com/docs/search/self-managed/current/deployment/compatibility-requirements/) directly instead of only checking `db.version()`.

For Community self-managed, product documentation lists supported Linux systems and corresponding deployment methods; do not treat MongoDB Community running directly on Windows or macOS as an equivalent self-managed Search environment. When developing on those machines, consider Atlas or a documented Linux/container environment.

### Checklist Before Enabling the Feature

1. **Server and Search:** record the Atlas tier or MongoDB Server version, `mongot`, topology, and supported OS.
2. **Connectivity:** the application reaches the right database/collection with proper TLS and authentication settings.
3. **Permissions:** the deployment account has `createSearchIndexes`, `updateSearchIndex`, `listSearchIndexes` when needed; the runtime/read account has read and query execution privileges. For example, the `readWrite` role is typically sufficient to manage indexes at the appropriate collection scope.
4. **Readiness:** Search index defined on the right collection, status `READY` and `queryable: true`.
5. **Client versions:** `mongosh`, Java Driver, and Spring Data MongoDB support the commands/APIs actually used; do not infer full Search support from a single annotation.
6. **Limits and cost:** test with real data, measure index size, CPU/RAM, indexing speed, search latency, and tier limits.

If Search requirements are not met, the application can intentionally choose a fallback search flow using `$text` or regular queries; differences in syntax, relevance, and features must be tested. Never silently assume the two mechanisms produce equivalent results.

## 8. Operations, Index Updates, and Performance

### Index Creation and Updates Are Asynchronous

After creating or modifying an index, the system needs time to build or rebuild the Search structure. While updating an existing index, the old definition may continue serving queries while the new one is built. Common statuses:

| Status | Interpretation and Action |
| --- | --- |
| `PENDING` | Build not yet started; new index is not queryable |
| `BUILDING` | Creating or rebuilding; check `queryable` before using |
| `READY` | Index is ready to serve queries |
| `FAILED` | Inspect the definition, fields, and error details |
| `STALE` | Queryable, but Search data risks lagging behind the collection |
| `DELETING` / `DOES_NOT_EXIST` | Do not use this index for queries |

**Consistency:** Search indexes synchronize from source data, so search results must not be relied upon for strict immediate read-after-write guarantees right after a write. If business logic requires immediate confirmation of a transaction or access permission, re-read the source document with an appropriate query.

### Reducing Cost and Improving Quality

- Choose `dynamic: false` for stable schemas; index only the required fields with the right query types.
- Use `compound.filter` for mandatory filtering to avoid unnecessary impact on relevance scores.
- Limit result counts and paginate with mechanisms supported by MongoDB Search; avoid loading all results and paginating in Java.
- Be cautious with fuzzy, wildcard, large gram ranges, and indexing long descriptions; measure p50/p95 latency with realistic queries.
- When changing analyzers, tokenization, or mappings, plan an index rebuild and test a new index version (`_v2`) before switching the index name in application config.
- Monitor index status, query errors, Search node/`mongot` resources, and the lag between write time and document discoverability.
- For multi-tenant data, always enforce tenant and permission constraints from the backend. You can index `tenantId` as `token` to filter inside `$search.compound.filter`, while also verifying permissions before returning data.

## 9. Common Troubleshooting

| Symptom | Causes to Check | Verification / Resolution |
| --- | --- | --- |
| Error saying `$search` is not supported | Running MongoDB without Search or wrong topology | Check deployment type, version, and Search component |
| Index created successfully but returns no results | Index still `BUILDING`, wrong index name, or field not mapped | Call `getSearchIndexes(...)`, compare `index` and `path` |
| Accented queries work, unaccented queries fail | Analyzer/tokenization not folding as expected | Test accented/unaccented pairs, inspect both analyzers, measure precision/recall |
| Results too broad or confusingly ordered | Analyzer over-tokenizes, condition is in `should`, or score skewed | Inspect `must` / `filter`, relevance algorithm, and sample data |
| Category filter does not match | Field type incompatible with `equals` or wrong value | Check `token` mapping and stored values |
| Search index not shown in `getIndexes()` | Search indexes are not listed among regular indexes | Use `getSearchIndexes()` or `$listSearchIndexes` |
| Stale Search index after config edit | Rebuild not yet finished | Watch status, wait for `READY` before comparing results |
| Permission error on create/update | Database user lacks Search index management privileges | Check database/collection roles and deployment mechanism |
| Latency spikes sharply | Too many fields, n-grams/fuzzy, overly large limits, under-resourced Search | Trim mappings, benchmark queries, enforce limits, and evaluate resources |

## 10. Self-Check Practice Tasks

**Task A — Mapping:** Add a `brand` field to the products collection. Design a `token` mapping if exact brand code filtering is needed, and consider adding a separate `string` mapping if you also want keyword search on brand names. Explain why two different query types are chosen.

**Task B — Analyzer:** Create one index version using `lucene.standard` and another using `vi_fold`. With at least 20 products, test accented/unaccented strings, uppercase names, compound names, and typos. Record true positives, false hits, and latency. Do not conclude which analyzer is better from a single example.

**Task C — Spring Data:** Extend the service to accept `category`, `maxPrice`, and `limit`. Validate inputs, cap `limit` at a reasonable threshold, and use `compound.filter`. Verify with an integration test against a real Search environment or an officially supported local environment. A standard MongoDB container without Search installed is not sufficient to test `$search`.

**Task D — Deployment:** Prepare a checklist recording the Atlas tier or MongoDB Server/`mongot` version, OS, database privileges, index name, index status, and test query results. If any condition fails, document its impact on the search feature before enabling any feature flag.

**Completion criteria:** Have a concrete Search index definition, be able to explain the analyzers used at index time and query time, execute `$search` via `MongoTemplate`, and prove that environment compatibility and `READY` status were verified.

## 11. Official Documentation

- [MongoDB Search — Index Reference](https://www.mongodb.com/docs/search/indexes/index-definitions/): `mappings`, analyzers, and definition options.
- [MongoDB Search — Token Filters](https://www.mongodb.com/docs/search/indexes/analyzers/token-filters/): `lowercase`, `asciiFolding`, `icuFolding`.
- [MongoDB — `$search`](https://www.mongodb.com/docs/search/query/aggregation-stages/search/): syntax, pipeline restrictions, and scoring.
- [MongoDB — `$searchMeta`](https://www.mongodb.com/docs/search/query/aggregation-stages/searchmeta/): metadata, counts, and facets.
- [MongoDB — Manage Search Indexes](https://www.mongodb.com/docs/search/indexes/manage-indexes/): creating, editing, listing, and Search index statuses.
- [MongoDB Search — Deployment Options](https://www.mongodb.com/docs/search/deployment/deployment-options/): testing options with Atlas and local deployments.
- [MongoDB Search Self-Managed — Compatibility Requirements](https://www.mongodb.com/docs/search/self-managed/current/deployment/compatibility-requirements/): verifying version-based support requirements.
- [Spring Data MongoDB — MongoDB Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mongo-search-indexes.html): Search index management/query APIs for your Spring Data version.

> Note: Supported versions, tiers, orchestration software, and Search limits change over time. Always consult the current compatibility page during deployment, especially for self-managed setups.
