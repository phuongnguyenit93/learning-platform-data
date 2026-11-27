# `TextCriteria`, `TextQuery`, and Full-Text Search in Spring Data MongoDB

An article management application may need to search for content containing “truy vấn MongoDB”, prioritize titles that match the keywords, exclude outdated documents, and paginate results. Filtering with ordinary string matching struggles to meet these requirements as the number of documents grows. MongoDB supports **text indexes** and the **`$text`** operator to search by indexed words; **Spring Data MongoDB** provides `TextCriteria` to express search conditions, `TextQuery` to build queries, and `MongoTemplate` or repositories to read the results.

This lesson belongs to the **Advanced Search** section of the `SPRING_DATA_MONGODB` module. After this lesson, you will be able to design a text index, distinguish keywords from phrases, search via Spring Data, retrieve relevance scores, and verify execution plans. Examples use Vietnamese to illustrate the limitations of MongoDB's language analysis mechanism.

## 1. How Does Full-Text Search Work?

A **text index** builds a lookup structure by words (*terms*) extracted from selected string fields. When receiving a `$text` query, MongoDB parses the search string, uses the index to find matching documents, and can compute a **`textScore`** for ranking. Unlike simple substring matching, the system operates on extracted words; results are affected by the index language, *stop words*, *stemming*, field weights, and search syntax.

| Component | Role | Example |
| --- | --- | --- |
| Text index | Specifies the fields included in the full-text index | `title`, `body` |
| `$text` | Search condition across fields in the text index | `{$text: {$search: "MongoDB index"}}` |
| `TextCriteria` | Builds `$text` search expressions in Java | `matchingAny("MongoDB", "Java")` |
| `TextQuery` | Wraps `TextCriteria` in a `Query`, optionally requesting and sorting by score | `TextQuery.queryText(criteria)` |
| `textScore` | Document relevance score for a query, used for ranking | `{score: {$meta: "textScore"}}` |

**Key limitation to know:** `$text` is word-based search; it does not natively support typo correction, mid-word substring matching, autocomplete, or deep Vietnamese analyzers. If the product requires fuzzy matching, instant suggestions, or complex ranking pipelines, evaluate MongoDB Search (Atlas Search, using `$search`) or a dedicated search engine. `$text` and the aggregation stage `$search` are two distinct mechanisms.

## 2. Preparing the Sample Dataset

The following documents simulate a tutorial library. Use `mongosh` or a MongoDB environment with write permissions to run the commands sequentially:

```javascript
db.articles.insertMany([
  {
    _id: "a1",
    title: "Tối ưu truy vấn MongoDB",
    body: "Học cách dùng chỉ mục, explain và đo hiệu năng truy vấn.",
    category: "database",
    published: true
  },
  {
    _id: "a2",
    title: "Tìm kiếm toàn văn với Spring Data MongoDB",
    body: "Sử dụng TextCriteria và TextQuery để tìm bài viết theo từ khóa.",
    category: "database",
    published: true
  },
  {
    _id: "a3",
    title: "Thiết kế ứng dụng Java",
    body: "Repository, kiểm thử và bảo trì ứng dụng Java.",
    category: "backend",
    published: true
  },
  {
    _id: "a4",
    title: "Truy vấn MongoDB cũ",
    body: "Tài liệu truy vấn cũ cần được cập nhật.",
    category: "database",
    published: false
  }
]);
```

This is illustrative data; running `insertMany` a second time with the same `_id` values will raise a duplicate key error. In a real application, seed data through a controlled process using stable identifiers and avoiding accidental duplicate records.

## 3. Creating a Text Index Aligned with Search Needs

### 3.1. Choosing Fields, Weights, and Language

Suppose you want to search across both title and body while prioritizing results where the keyword appears in the title:

```javascript
db.articles.createIndex(
  { title: "text", body: "text" },
  {
    name: "articles_fulltext",
    weights: { title: 5, body: 1 },
    default_language: "none"
  }
);
```

Explanation:

- `title: "text"` and `body: "text"` declare the indexed fields. A `$text` query searches **all fields belonging to this collection's text index**, rather than picking an arbitrary field at query time.
- `weights` increase the contribution of terms appearing in `title` relative to `body` when scoring. Weights assist ranking but do not guarantee a fixed score formula or ordering across all datasets and versions.
- `default_language: "none"` disables *stop word* removal and *stemming* for a specific language. This is worth considering for the Vietnamese example because a Vietnamese *stemmer* is not provided as a supported language in MongoDB's classic text index. It does **not** add semantic understanding or Vietnamese compound-word segmentation.

If the dataset is English, you can choose `default_language: "english"` to apply the corresponding language rules. A multilingual collection can use a per-document language field configured via `language_override`, but only use language values supported by MongoDB and test results on real data.

**Important constraint:** Each collection can have only **one** classic text index. To search across multiple fields, include those fields in the same index. You cannot create one independent text index for `title` and another independent text index for `body` on the same collection. Changing fields, weights, or language configuration must go through an index migration process; do not assume `createIndex` will silently replace an existing index that has the same field set but different options.

To inspect the actual index:

```javascript
db.articles.getIndexes();
```

### 3.2. When to Use a Compound Text Index?

If **every** full-text query is strictly scoped by a `tenantId`, you can consider a compound index with an equality field first followed by the text fields:

```javascript
// Alternative design example; DO NOT run this additionally on the
// articles collection that already has articles_fulltext: one collection can have only one text index.
db.tenant_articles.createIndex(
  { tenantId: 1, title: "text", body: "text" },
  { name: "tenant_articles_text", default_language: "none" }
);
```

With a compound text index where a regular field precedes the text fields, a `$text` query must include an **equality** condition on those prefix fields to use the index. Choose this design only when business rules and actual queries are consistent; do not put a prefix field if the application still needs to perform full-text searches across the entire collection without specifying that field.

## 4. Understanding `$text` Syntax in MongoDB

### 4.1. Searching by Keywords

```javascript
db.articles.find({
  $text: { $search: "MongoDB Java" }
});
```

With standard syntax, terms parsed from the search string have **OR** semantics: documents matching any one of the words may be returned. The query above can match documents containing `MongoDB` or `Java`; it does not require both words to appear together. If the feature requires an exact phrase, use phrase search.

### 4.2. Exact Phrase Search and Term Exclusion

```javascript
// Double quotes are INSIDE the $search string.
db.articles.find({
  $text: { $search: '"truy vấn" -cũ' }
});
```

`"truy vấn"` requires the phrase in the exact order of indexed terms. `-cũ` excludes documents matching the term `cũ`. On the sample dataset, this is the closest expression to “find articles containing the phrase truy vấn while excluding old ones”. However, phrase matching still relies on the text index tokenizer; test with punctuation, Vietnamese text, and long text fields.

Distinguish three requirements:

| Requirement | Appropriate Expression | Notes |
| --- | --- | --- |
| Contains at least one word from `MongoDB Java` | `$search: "MongoDB Java"` | OR semantics between terms |
| Contains the phrase `truy vấn` | `$search: '\"truy vấn\"'` | Double quotes are part of the search string |
| Contains the phrase `truy vấn`, excludes `cũ` | `$search: '\"truy vấn\" -cũ'` | The `-` sign applies to the excluded term |

By default, MongoDB full-text search is generally case-insensitive and diacritic-insensitive under modern text index rules; you can adjust `$caseSensitive` and `$diacriticSensitive` when needed. Do not rely on default behavior for proper nouns requiring exact matching; if business rules require exact matching, consider a normalized field or a separate equality condition.

### 4.3. Ranking by Relevance

Full-text search does not return documents in a user-meaningful order by default. Request `textScore` and sort by score:

```javascript
db.articles.find(
  { $text: { $search: "MongoDB truy vấn" } },
  {
    title: 1,
    category: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).limit(10);
```

The score is a **relative measure within a single query**, not a true probability or match percentage. Only compare scores of documents evaluated under the same query and index configuration. If multiple documents share the same score and stable pagination is needed, define a secondary sort policy and thoroughly test stability as data changes.

## 5. Mapping Entities and Text Indexes in Spring Data MongoDB

Spring Data supports `@TextIndexed` on properties to include in the text index and `@TextScore` on the property receiving the search score.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.TextIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.TextScore;

@Document(collection = "articles")
public class Article {
    @Id
    private String id;

    @TextIndexed(weight = 5)
    private String title;

    @TextIndexed
    private String body;

    private String category;
    private boolean published;

    @TextScore
    private Float score;

    protected Article() {}

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getBody() { return body; }
    public String getCategory() { return category; }
    public boolean isPublished() { return published; }
    public Float getScore() { return score; }
}
```

`@TextIndexed` describes which fields should be indexed, while the text index in MongoDB must actually exist. In modern Spring Data MongoDB versions, **automatic index creation is disabled by default**. It can be enabled in development environments:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

In applications with explicit requirements such as `default_language: "none"` and `weights`, a more controllable approach is **managing indexes via migrations**, such as the `createIndex` command in section 3. If you choose to enable annotation-based auto-index creation, configure the corresponding language and avoid letting auto-creation collide with migration-managed indexes. Changing an annotation does not cause MongoDB to automatically drop and recreate the old index.

## 6. Writing Queries with `TextCriteria`

`TextCriteria` provides an API to express the components of a `$search` string without manually assembling JSON query strings.

```java
import org.springframework.data.mongodb.core.query.TextCriteria;

// Find documents containing at least one of the analyzed words.
TextCriteria anyWord = TextCriteria.forDefaultLanguage()
    .matchingAny("MongoDB", "Java");

// Search for the phrase "truy vấn" and exclude the term "cũ".
TextCriteria phraseWithoutOld = TextCriteria.forDefaultLanguage()
    .matchingPhrase("truy vấn")
    .notMatching("cũ");

// Search using a specified language when the index supports that language.
TextCriteria english = TextCriteria.forLanguage("english")
    .matching("query");
```

| API | Meaning | Equivalent Intent |
| --- | --- | --- |
| `forDefaultLanguage()` | Uses the index's default language | No separate `$language` needed |
| `forLanguage("english")` | Specifies the query language | `$language: "english"` |
| `matching("MongoDB")` | Adds a regular word/term expression | A term in `$search` |
| `matchingAny("MongoDB", "Java")` | Matches any of the terms | Multiple terms with OR semantics |
| `matchingPhrase("truy vấn")` | Searches for a phrase | Phrase inside double quotes |
| `notMatching("cũ")` | Excludes a term | Term prefixed with `-` |

`TextCriteria` describes MongoDB's text-search syntax; it does not automatically add conditions like `published = true` or `category = "database"`. Those business filters are added to `Query` using `Criteria` in the next step.

## 7. Using `TextQuery` and `MongoTemplate` to Retrieve Results

Example service that takes a phrase input, filters for published articles in the `database` category, ranks by score, and limits to 10 results:

```java
import java.util.List;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;

public class ArticleSearchService {
    private final MongoTemplate mongoTemplate;

    public ArticleSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Article> searchPublishedArticles(String phrase) {
        TextCriteria textCriteria = TextCriteria.forDefaultLanguage()
            .matchingPhrase(phrase);

        TextQuery query = TextQuery.queryText(textCriteria)
            .sortByScore()
            .includeScore();

        query.addCriteria(Criteria.where("published").is(true)
            .and("category").is("database"));
        query.limit(10);

        return mongoTemplate.find(query, Article.class);
    }
}
```

Example invocation:

```java
List<Article> articles = articleSearchService
    .searchPublishedArticles("truy vấn");

for (Article article : articles) {
    System.out.printf("%s | score=%s%n",
        article.getTitle(), article.getScore());
}
```

Points to understand:

1. `TextQuery.queryText(textCriteria)` creates a `Query` with a `$text` condition.
2. `sortByScore()` requests ordering by relevance, while `includeScore()` adds the score to the projection so it maps to the `@TextScore` property.
3. `Criteria` adds regular filter conditions; it does not alter phrase syntax inside `TextCriteria`.
4. `limit(10)` caps the number of returned documents. For multi-page data, clearly specify sort conditions and handle data mutations to avoid duplicate or skipped results across pages.

In real projects, validate the search string length and prevent users from accidentally entering syntax such as `-term` or quotes when the UI only expects plain text. `TextCriteria` builds the query structure safely while preserving the full-text search semantics of the input string.

### 7.1. Searching by Multiple Words Instead of a Phrase

When a search box needs documents containing *any* of the user's words, use `matchingAny`:

```java
TextCriteria criteria = TextCriteria.forDefaultLanguage()
    .matchingAny("MongoDB", "Java");

TextQuery query = TextQuery.queryText(criteria)
    .sortByScore()
    .includeScore();
query.limit(20);

List<Article> results = mongoTemplate.find(query, Article.class);
```

`matchingAny` typically produces broader results than `matchingPhrase`. When evaluating search accuracy, compare both queries against the same dataset and clarify to users whether the search box matches any word or an exact phrase.

## 8. When Is Repository-Based Full-Text Search Appropriate?

A repository can expose a method using `@Query` with a simple `$text` condition:

```java
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ArticleRepository extends MongoRepository<Article, String> {
    @Query("{ '$text': { '$search': ?0 } }")
    List<Article> searchText(String searchExpression);
}
```

Calling `searchText("MongoDB Java")` uses MongoDB `$text` term semantics. This example is for simple queries; it **does not automatically sort by `textScore` or include the score in the projection**. When you need dynamic filters, phrase queries, custom projections, or relevance sorting, `TextCriteria` + `TextQuery` + `MongoTemplate` is usually clearer and easier to control. You can build a custom repository to encapsulate that logic for the business layer.

In repository or service methods, avoid treating `$text` as a substring filter. For instance, searching `Mongo` will not necessarily match the word `MongoDB`; if you want prefix or fuzzy matching, design with a different tool.

## 9. Reading `explain()` and Diagnosing Performance

A simple measurement in MongoDB:

```javascript
db.articles.find(
  {
    $text: { $search: "MongoDB truy vấn" },
    published: true,
    category: "database"
  },
  {
    title: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
}).limit(10).explain("executionStats");
```

In the `explain` output, verify that the query uses the expected text index and inspect `nReturned`, `totalKeysExamined`, `totalDocsExamined`, and the full-text search stage details. Stage names such as `TEXT_MATCH` may vary between MongoDB versions; evaluate the **actual execution plan and number of examined records**, rather than coupling diagnostic logic to a single stage name string.

Effective optimization practices:

- **Choose indexed fields deliberately.** Indexing every text field increases storage size and write overhead, while not every field improves result quality.
- **Use appropriate weights.** For articles, keywords in the title are typically more valuable than the same keyword in a long body; tune weights based on data and evaluation criteria.
- **Combine business filters.** Conditions such as `published`, `category`, or access permissions must be applied in the query itself; do not fetch many results and filter everything in Java.
- **Limit projections and result counts.** Return only the fields needed for display, and account for data volume when users paginate deeply.
- **Measure both quality and speed.** A text index can be fast yet still fail to return the articles users expect. Prepare a set of test queries and expected results to evaluate alongside `explain` metrics.

Note: If a collection uses a compound text index with regular prefix fields, queries must include equality conditions on those prefix fields to use the index. Furthermore, you cannot optimize every query by creating additional independent text indexes on the same collection.

## 10. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `$text` reports missing text index | Index not created or connected to the wrong collection/database | Check `db.articles.getIndexes()` and verify the application's database |
| Results not ordered by relevance | Missing sort by `$meta: "textScore"` | Use `sortByScore()` or sort by `$meta` |
| `score` is always `null` in the entity | Score not projected or mapping mismatch | Check `@TextScore`, `includeScore()`, and returned data |
| Searching “truy vấn” matches too many articles | Separate words in the string have OR semantics | Switch to `matchingPhrase("truy vấn")` when a phrase is desired |
| Vietnamese words not analyzed as expected | Using English stemming/stop words or unsuitable tokenization | Review `default_language`, consider `none`, test with real keywords |
| Query does not match words missing a few characters | `$text` does not support fuzzy/substring by default | Consider MongoDB Search/autocomplete or an appropriate engine |
| Error when trying to create another text index | MongoDB limits each collection to one classic text index | Redesign the existing index to include the required fields |
| Results include unauthorized articles | Query only has `$text`, missing access-control filters | Add tenant, visibility, and permission filters before returning results |

## 11. Practice: Building an Article Search Feature

1. Run `insertMany` from section 2 and create the text index with `weights` and `default_language: "none"` from section 3. Verify with `getIndexes()`.
2. Use `$text` to search `MongoDB Java` and compare the results against searching the phrase `"truy vấn"`. Explain why the two queries return different result sets.
3. Try `"truy vấn" -cũ`, then add `published: true` to observe how full-text conditions and business filters complement each other.
4. Run `TextCriteria.forDefaultLanguage().matchingPhrase("truy vấn")` via `TextQuery`; call `sortByScore()` and `includeScore()`, then print the title and score from `@TextScore`.
5. Run `explain("executionStats")`, record the index used and the number of documents examined. Experiment with adjusting weights in a practice environment by recreating the text index, then compare the result ordering.
6. Test strings such as `Mongo`, `MongoDB`, `java`, `Java`, accented words, and unaccented words. Document any surprising behaviors; use them to define your product's Vietnamese search requirements.

## 12. Design Decision Summary

Choose **text index + `$text`** when you need to search terms across one or more text fields and want a direct MongoDB setup. In Spring Data MongoDB, use **`TextCriteria`** to express terms, phrases, and exclusions; use **`TextQuery`** to attach conditions to the query, sort by `textScore`, and map scores to the entity. For Vietnamese data, language settings and tokenization must be tested thoroughly; classic text indexes do not replace a full-featured natural language search engine. When a product requires autocomplete, fuzzy search, or advanced ranking, evaluate a dedicated search system based on actual requirements.
