# Text Index, `@TextIndexed`, and `@Language` in Spring Data MongoDB

## Objectives and Context

When building a search feature for articles, documents, or products, users enter a few keywords instead of knowing the exact value of a field. MongoDB provides a **text index** to search for words within analyzed content using the `$text` operator. Spring Data MongoDB supports declaring indexes with `@TextIndexed`, selecting languages with `@Document(language = ...)` and `@Language`, as well as searching via `MongoTemplate`, `TextCriteria`, and `TextQuery`.

After this lesson, you will be able to explain how a text index works, create a multi-field index with appropriate weights, distinguish between the default language and per-document languages, query with relevance scores, and diagnose real-world errors.

**Scope:** This is MongoDB's *native* text index. **MongoDB Search** uses its own index and analyzer with the `$search` operator, which is suitable for autocomplete, fuzzy matching, language analysis, and more complex ranking.

## 1. How Does a Text Index Work?

Suppose a system stores tutorial articles in the `articles` collection:

```javascript
db.articles.insertMany([
  {
    title: "Spring Data MongoDB guide",
    body: "Create indexes and query MongoDB documents with Spring Data",
    contentLanguage: "english"
  },
  {
    title: "MongoDB search fundamentals",
    body: "Learn text indexing, search scoring and query design",
    contentLanguage: "english"
  },
  {
    title: "Introducción a MongoDB",
    body: "Aprende a buscar documentos con índices de texto",
    contentLanguage: "spanish"
  }
]);
```

Create a text index combining two fields:

```javascript
db.articles.createIndex(
  { title: "text", body: "text" },
  {
    name: "article_text_idx",
    weights: { title: 5, body: 1 },
    default_language: "english",
    language_override: "contentLanguage"
  }
);

db.articles.find({ $text: { $search: "mongodb" } });
```

MongoDB indexes text by **terms** and processes them according to language rules: it can remove **stop words** like `the` in English, and use **stemming** to reduce word forms to an approximate root. Therefore, `$text` searches for indexed terms; it is **not** an arbitrary substring search operator like `contains`.

`weights` increase the relative contribution of a field to `textScore`. In the example above, a keyword appearing in `title` generally has a greater impact than a word in `body`, though the final score also depends on document statistics and terms.

| Mechanism | Characteristics | Use Case |
| --- | --- | --- |
| Regular index (`@Indexed`) | Supports equality filters, range queries, and some prefix queries | Codes, dates, statuses, lookup keys |
| Text index + `$text` | Searches terms across multiple fields with language rules | Basic keyword search in titles, content |
| `$regex` | Matches string patterns; only certain patterns use indexes effectively | Simple pattern or prefix matching |
| MongoDB Search | Dedicated search index and analyzers | Autocomplete, fuzzy, synonyms, advanced ranking |

Key takeaways:

- A collection can have **at most one text index**, though that index can include multiple fields.
- Terms in a search string `$search: "spring mongodb"` are combined with **OR** by default. To search for a phrase, enclose the phrase in double quotes inside the `$search` string itself.
- A `$text` query requires an existing text index, and results are not automatically sorted by relevance.
- Depending on the text index version and query options, searches may be case-insensitive and diacritic-insensitive. Always verify against real data.

## 2. Declaring `@TextIndexed`, `@Language`, and `@TextScore`

Add `spring-boot-starter-data-mongodb` compatible with your Spring Boot version, configure the connection, and create the entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Language;
import org.springframework.data.mongodb.core.index.TextIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.TextScore;

@Document(collection = "articles", language = "english")
public class Article {

    @Id
    private String id;

    @TextIndexed(weight = 5)
    private String title;

    @TextIndexed
    private String body;

    @Language
    private String contentLanguage;

    @TextScore
    private Float score;

    // Constructors, getters, and setters omitted.
}
```

| Component | Role |
| --- | --- |
| `@Document(collection = "articles")` | Maps the entity to the `articles` collection |
| `@Document(language = "english")` | Specifies the **default language for the text index** created from the entity |
| `@TextIndexed` | Includes the field in the collection's single text index |
| `@TextIndexed(weight = 5)` | Sets the relative weight; defaults to 1 |
| `@Language` | Marks the property holding the **per-document language**, used during indexing |
| `@TextScore` | Receives relevance score metadata from `$text` queries; not persisted as a regular data field |

The two `@TextIndexed` annotations above create **one index definition**, not two independent indexes. With `@Language` placed on `contentLanguage`, Spring Data uses this property as the language override field; in MongoDB this corresponds to the `language_override: "contentLanguage"` option. For example, a document with `contentLanguage: "spanish"` will be analyzed using Spanish rules; documents without an override use `default_language`, which is `english`.

**Exact distinction:** `@Language` does not make `contentLanguage` a full-text searchable field. It only determines how the `@TextIndexed` fields are analyzed. The language stored in the document and the language of the *query* are two different concepts.

### Indexing Nested Fields

```java
@Document(collection = "knowledge")
class KnowledgeItem {
    @TextIndexed(weight = 4)
    String title;

    Summary summary;
}

class Summary {
    @TextIndexed(weight = 2)
    String description;
}
```

Spring Data can index paths such as `title` and `summary.description`. When using `@Field` to rename fields, verify the actual key names in the database. Do not assume that every field inside a nested object is automatically text-indexed.

## 3. Creating the Actual Index in MongoDB

Annotations are only **metadata** for Spring Data. Since Spring Data MongoDB 3.0, automatic index creation is **disabled** by default. For learning or development environments, you can enable it in Spring Boot:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

In production environments, indexes should be created and modified through migrations or controlled deployment pipelines because building an index on a large collection is resource-intensive.

If you want to explicitly create indexes from the entity's annotations:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;
import org.springframework.stereotype.Component;

@Component
public class ArticleIndexInitializer {
    private final MongoTemplate mongoTemplate;

    public ArticleIndexInitializer(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void createIndexes() {
        var resolver = new MongoPersistentEntityIndexResolver(
            mongoTemplate.getConverter().getMappingContext()
        );

        resolver.resolveIndexFor(Article.class)
            .forEach(index -> mongoTemplate.indexOps(Article.class).ensureIndex(index));
    }
}
```

This is an example for **a single** entity; in production, choose one clear source of index management to avoid overlapping configurations. You can also use the direct `createIndex` command from section 1 if your migration tool is responsible for index creation.

Verify after the application starts:

```javascript
db.articles.getIndexes();
```

Check that `weights` includes both `title` and `body`, along with the `default_language` and `language_override` options. Depending on the MongoDB version, the internal keys of a text index may be displayed as `_fts`/`_ftsx` instead of the original declaration.

Changing the field list, weight, or language on annotations **does not automatically update** an existing index. An appropriate migration is required (usually dropping and recreating the text index), taking storage and rebuild time into account.

## 4. Searching with `MongoTemplate` and Ranking by `textScore`

Use `TextCriteria` and `TextQuery` to build queries instead of manually concatenating BSON strings:

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;
import org.springframework.stereotype.Service;

@Service
public class ArticleSearchService {
    private final MongoTemplate mongoTemplate;

    public ArticleSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Article> search(String input, int requestedLimit) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Keyword must not be blank");
        }

        TextCriteria criteria = TextCriteria.forDefaultLanguage()
            .matching(input.trim());

        TextQuery query = TextQuery.queryText(criteria)
            .sortByScore()
            .includeScore();

        query.limit(Math.min(Math.max(requestedLimit, 1), 100));
        return mongoTemplate.find(query, Article.class);
    }
}
```

`sortByScore()` adds sorting by the `textScore` metadata; `includeScore()` includes this metadata in the results. When the entity has `@TextScore Float score`, Spring Data maps the score to the `score` property. The score is not a probability and is not suitable for absolute comparison across different indexes or datasets. For ordinary read queries, `score` may be `null`.

The equivalent MongoDB command:

```javascript
db.articles.find(
  { $text: { $search: "mongodb" } },
  { title: 1, body: 1, score: { $meta: "textScore" } }
).sort({ score: { $meta: "textScore" } });
```

### Common Query Patterns

```java
// Contains at least one of the terms.
TextCriteria any = TextCriteria.forDefaultLanguage()
    .matchingAny("spring", "mongodb");

// Contains a phrase according to $text term analysis.
TextCriteria phrase = TextCriteria.forDefaultLanguage()
    .matchingPhrase("spring data");

// Contains mongodb, excluding documents with the term legacy.
TextCriteria exclude = TextCriteria.forDefaultLanguage()
    .matching("mongodb")
    .notMatching("legacy");

// Analyzes query terms in Spanish.
TextCriteria spanish = TextCriteria.forLanguage("spanish")
    .matching("documentos");

List<Article> matches = mongoTemplate.find(
    TextQuery.queryText(spanish).sortByScore(),
    Article.class
);
```

Phrase searching with `matchingPhrase("spring data")` differs from the OR behavior of `matchingAny("spring", "data")`. You can use `caseSensitive(true)` and `diacriticSensitive(true)` on `TextCriteria` if case or diacritic sensitivity is required; verify the actual results and query cost.

**`@Language` and `TextCriteria.forLanguage(...)` are not interchangeable.** The annotation affects *how documents are indexed*, while `forLanguage` affects *how the search keywords passed to the query are analyzed*. Choosing the right language when indexing data is crucial.

## 5. Languages and the Vietnamese Case

MongoDB supports a specific set of languages for native text indexes, such as `english`, `spanish`, `french`, `german`, `portuguese`, and others. This language governs stop words and stemming. For multilingual documents in supported languages, each document can contain an override:

```javascript
db.articles.insertOne({
  title: "Aprender Spring Data",
  body: "Guía para buscar documentos",
  contentLanguage: "spanish"
});

db.articles.find({
  $text: { $search: "documentos", $language: "spanish" }
});
```

If a document has no override field, the index uses `default_language`. Do not store arbitrary language values: MongoDB requires a supported language name or code.

### Important Limitation for Vietnamese Data

**MongoDB's native text index does not have a Vietnamese analyzer.** Setting `@Document(language = "vietnamese")` or `TextCriteria.forLanguage("vi")` does not provide Vietnamese language processing and may throw an unsupported language error.

If you only need to search for simple terms, choose the `none` language to disable stop words and stemming from other languages:

```java
@Document(collection = "vietnamese_articles", language = "none")
class VietnameseArticle {
    @Id String id;
    @TextIndexed(weight = 4) String title;
    @TextIndexed String body;
}
```

Or via `mongosh`:

```javascript
db.vietnamese_articles.createIndex(
  { title: "text", body: "text" },
  { default_language: "none", weights: { title: 4, body: 1 } }
);
```

`none` does **not** turn MongoDB into a Vietnamese word-segmentation or semantic engine: it does not accurately handle multi-syllable words, synonyms, typos, or typeahead suggestions. To implement full-featured Vietnamese search, you need to design an appropriate analyzer and search pipeline (such as MongoDB Search or a dedicated search engine). If you build a normalized text field for accent-insensitive search, you must apply the exact same normalization rules at both index time and query time, and test with real Vietnamese data.

| Data | Reasonable Configuration | Limitations |
| --- | --- | --- |
| Mostly English | `@Document(language = "english")` | English stop words and stemming |
| English and Spanish | Default `english`, per-record `@Language` | Queries need the matching language |
| Vietnamese, basic term search | `@Document(language = "none")` | No Vietnamese semantic analysis |
| Multilingual, typo tolerance, and suggestions | MongoDB Search / search engine | Requires dedicated search index/analyzer |

## 6. End-to-End Verification and Performance Observation

After creating the index and inserting the data from section 1, run these in sequence:

```javascript
// Is there one text index with two fields and a language override?
db.articles.getIndexes();

// Can terms appearing in title or body be found?
db.articles.find({ $text: { $search: "spring" } });

// Can consecutive phrase terms be found?
db.articles.find({ $text: { $search: '"spring data"' } });

// Are the score and result order reasonable?
db.articles.find(
  { $text: { $search: "mongodb" } },
  { title: 1, score: { $meta: "textScore" } }
).sort({ score: { $meta: "textScore" } });

// Use execution plan and stats for diagnostics.
db.articles.find({ $text: { $search: "spring" } })
  .explain("executionStats");
```

Add one document containing the keyword only in `body` and one containing the keyword in `title` to prove both fields are indexed. Compare results before and after changing weights **in a test environment**; scores can vary with content and term frequency, so you cannot assume a document will always rank first solely because of a higher weight.

Inspect `explain("executionStats")` to compare the number of scanned documents/index entries and execution cost. The stages inside the execution plan depend on the MongoDB version; do not rely on a single stage name across all environments. When measuring performance, use a realistic dataset size rather than just a few documents.

## 7. Limitations and Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `text index required for $text query` | Collection has no text index | Check `getIndexes()`, collection name, and index creation process |
| `@TextIndexed` is present but DB has no index | Auto-index creation is disabled | Enable intentionally in dev or use migration/`IndexResolver` |
| Cannot create a second text index | A collection can have at most one text index | Merge fields into the single index or run a migration |
| Common term search returns nothing | Term is a stop word for the language | Check `default_language` and `@Language` |
| Vietnamese search behaves unexpectedly | No Vietnamese analyzer in native text index | Try `none` or switch to a dedicated search engine |
| `score == null` | Query is not `$text` or score not requested | Use `TextQuery.includeScore()` or `sortByScore()` |
| Changed weight but results stay the same | Old index has not been rebuilt | Run an index migration, verify with `getIndexes()` |
| Searching `data` does not find `database` | `$text` does not match arbitrary substrings | Choose a search mechanism suited to the requirement |

Additional limitations of MongoDB text indexes:

1. **One text index per collection.** Queries containing `$text` cannot call `hint()` to force another index.
2. **Text indexes do not optimize ordinary sorting.** Sorting by date, name, or other fields requires separate index and query plan considerations.
3. **Compound text indexes have strict rules.** If regular keys precede text keys, a `$text` query must include equality conditions on those leading keys; text keys must be contiguous. They cannot be arbitrarily combined with several special index types.
4. **Indexes have storage and write overhead.** Updating text content requires updating the index; rebuilding an index on a large collection requires operational planning.
5. **Pagination requires a deterministic order.** Two documents can have the same `textScore`; when paginating results, you must account for tie-breaker criteria, input limits, result limits, and verify on the server/driver version in use.

## 8. Practice Exercises

**Exercise 1 — Configuration:** Create a `knowledge_items` collection with `title`, `description`, `tags`, and `contentLanguage`. Configure title weight 8 and description weight 2. Create the index via annotations and verify fields and weights using `getIndexes()`. Explain why there is only one text index.

**Exercise 2 — Languages:** Insert English and Spanish articles. Attach `@Language` and compare `forDefaultLanguage()` queries against `forLanguage("spanish")`. Identify cases where stop words or stemming alter the results.

**Exercise 3 — Ranking:** Insert an article with the term only in `title`, one with the term only in `body`, and one containing the term in both. Return `textScore`, measure the actual ordering, and describe the effect of weights. Try changing the index via migration on test data.

**Exercise 4 — Vietnamese:** Create a separate collection with `language = "none"`. Test single words, multi-syllable phrases, accented/unaccented variants, and synonyms. Record the capabilities and limitations, then recommend when MongoDB Search is needed.

**Expected outcome:** Ability to create, inspect, query, and explain text indexes; distinguish `@TextIndexed`, `@Language`, query language, and `textScore`; and articulate the limitations with Vietnamese text.

## 9. References

- [Spring Data MongoDB — Index Creation / Text Indexes](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
- [Spring Data MongoDB — Full-text Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data MongoDB — TextCriteria API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/TextCriteria.html)
- [MongoDB Manual — $text Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Manual — Text Search Languages](https://www.mongodb.com/docs/manual/reference/text-search-languages/)
- [MongoDB Manual — Text Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/text-index-restrictions/)
