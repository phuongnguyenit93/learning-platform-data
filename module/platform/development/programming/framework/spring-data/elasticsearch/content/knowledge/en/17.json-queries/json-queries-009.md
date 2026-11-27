# `@SearchTemplateQuery` When Supported by Your Spring Data Version

Spring Data Elasticsearch supports Elasticsearch Search Templates so applications can reuse a Query DSL template stored on the cluster. When you want a Repository method to invoke a stored search template directly, you can place the `@SearchTemplateQuery` annotation on that method.

This annotation specifies the template ID. Spring Data sends Repository method parameters to the template as key/value pairs, where the key is the method parameter name and the value is the runtime argument. Therefore, parameter names on the method must match the Mustache placeholders in the template.

Important version notes:

- `SearchTemplateQuery` (the query object used in custom repositories) has been available since Spring Data Elasticsearch **5.1**.
- The `@SearchTemplateQuery` annotation for Repository methods has been available since **5.5**.
- If a project uses Spring Data Elasticsearch older than 5.5, this annotation cannot be used; you can use `SearchTemplateQuery` via a custom repository if the version is 5.1 or newer.
- For versions older than 5.1, use another query API or upgrade Spring Data Elasticsearch.

## 1. What Is a Search Template?

A Search Template is a query template saved in Elasticsearch as a stored script. Templates typically use the Mustache language to accept parameters at runtime. Instead of sending the entire Query DSL structure from the application on every request, the application sends only the template ID and parameter values.

For example, a template searching books by title might contain the `{{title}}` placeholder:

```json
{
  "query": {
    "match": {
      "title": "{{title}}"
    }
  }
}
```

When the application passes `title = "Spring Data"`, Elasticsearch renders the template into Query DSL with that search value and executes the search.

Execution flow:

```text
Cluster deployment / administration
          |
          | Register Mustache stored script
          v
Elasticsearch: script id = book-by-title

Spring Data Repository
          |
          | @SearchTemplateQuery(id = "book-by-title")
          | title = "Spring Data"
          v
Spring Data Elasticsearch
          |
          | Search template request
          v
Elasticsearch renders Mustache template
          |
          v
Execute Query DSL and return SearchHits
```

Because the template is stored on the cluster, it can be reused by multiple application instances or multiple services permitted to invoke it. Template content has its own deployment lifecycle independent of Java code; updating the stored template can change search results without changing the Repository interface.

## 2. Difference Between `@SearchTemplateQuery` and `SearchTemplateQuery`

These two names are similar, but they are two APIs at different layers:

| Component | Package | Since | Purpose |
|---|---|---:|---|
| `@SearchTemplateQuery` | `org.springframework.data.elasticsearch.annotations` | 5.5 | Marks a Repository method to use a stored search template. |
| `SearchTemplateQuery` | `org.springframework.data.elasticsearch.core.query` | 5.1 | Query object allowing custom repositories to invoke templates via `ElasticsearchOperations`. |
| `SearchTemplateQueryBuilder` | `org.springframework.data.elasticsearch.core.query` | 5.1 | Builder for configuring template ID/source and parameter map on the query object. |

The annotation only needs the `id` of the stored template. The query object is more flexible because it accepts a `Map<String, Object>` via `withParams(...)`, which suits cases where the application constructs the parameter map manually, integrates `Pageable`, or uses Spring Data Elasticsearch 5.1–5.4.

Do not confuse `@SearchTemplateQuery` with `@Query`. `@Query` accepts inline Query DSL JSON in the annotation; `@SearchTemplateQuery` references a template registered in Elasticsearch.

## 3. Registering a Stored Search Template

Before calling the Repository method, the template must exist in Elasticsearch. Spring Data provides `ScriptOperations`; the `ElasticsearchOperations` interface extends this capability and can be used to register stored scripts.

Example registering a template to search books by title:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.script.Script;
import org.springframework.stereotype.Component;

@Component
public class SearchTemplateProvisioner {

    private final ElasticsearchOperations operations;

    public SearchTemplateProvisioner(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void registerBookSearchTemplate() {
        Script script = Script.builder()
                .withId("book-by-title")
                .withLanguage("mustache")
                .withSource("""
                        {
                          "query": {
                            "match": {
                              "title": "{{title}}"
                            }
                          }
                        }
                        """)
                .build();

        operations.putScript(script);
    }
}
```

Key parts:

- `withId("book-by-title")` sets the stored script ID; the Repository method references this exact ID.
- `withLanguage("mustache")` declares the template language. Search templates use Mustache.
- `withSource(...)` holds the Query DSL body with placeholders.
- `putScript(...)` uploads the stored script to the cluster.

Register or update templates during an appropriate provisioning or deployment step rather than calling `putScript` on every search request. When modifying a template, control versions and test thoroughly before updating an ID actively used by applications.

You can also register the script directly through the Elasticsearch Stored Scripts API:

```http
PUT /_scripts/book-by-title
Content-Type: application/json

{
  "script": {
    "lang": "mustache",
    "source": "{ \"query\": { \"match\": { \"title\": \"{{title}}\" } } }"
  }
}
```

Both approaches create the same stored script. If you manage templates through the REST API or deployment tooling, the runtime application only needs search/execution privileges and does not require stored-script admin privileges.

## 4. Using `@SearchTemplateQuery` on Repository Methods

When a project uses Spring Data Elasticsearch **5.5 or newer**, you can import the annotation and place it on a method:

```java
import org.springframework.data.elasticsearch.annotations.SearchTemplateQuery;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface BookRepository
        extends ElasticsearchRepository<Book, String> {

    @SearchTemplateQuery(id = "book-by-title")
    SearchHits<Book> findByTitle(String title);
}
```

When invoked:

```java
SearchHits<Book> hits = bookRepository.findByTitle("Spring Data");
```

Spring Data uses template ID `book-by-title` and passes parameter `title` with value `Spring Data`. The `{{title}}` placeholder in the stored script is rendered with this value.

In the example, the Java parameter name is `title`, matching the Mustache placeholder name. If you change the method to `findByTitle(String searchText)`, the key sent will be `searchText`; the template still expects `title` and will not receive the intended value. Keep parameter names synchronized with the template and ensure the build preserves parameter name metadata for Spring Data (typically by enabling the `-parameters` compiler option if not already enabled).

The annotation has a required `id` attribute; it has no `params` attribute for declaring a map or `?0` positional placeholder syntax like `@Query`. Values are passed by method parameter name.

### Return Types of Repository Methods

The Spring Data Elasticsearch documentation demonstrates `SearchHits<Book>` for Repository methods using `@SearchTemplateQuery`. This type preserves per-hit details, scores, and search metadata.

```java
SearchHits<Book> hits = bookRepository.findByTitle("Spring Data");

List<Book> books = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
```

Supported repository return types also depend on query execution and the Spring Data version. When search metadata or scores are needed, `SearchHits<T>` is a clear choice. When designing methods returning `Page`, `SearchPage`, or `List`, verify that the return type is supported for this query kind and how the template handles pagination.

## 5. Templates with Multiple Parameters

A template can accept multiple values. Example searching books by title and filtering by category:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "title": "{{title}}"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "category": "{{category}}"
          }
        }
      ]
    }
  }
}
```

Repository method:

```java
public interface BookRepository
        extends ElasticsearchRepository<Book, String> {

    @SearchTemplateQuery(id = "book-by-title-and-category")
    SearchHits<Book> findByTitleAndCategory(String title, String category);
}
```

The two parameter names must match `{{title}}` and `{{category}}`. When invoked:

```java
SearchHits<Book> hits =
        bookRepository.findByTitleAndCategory("Spring Data", "TECHNICAL");
```

Spring Data passes both corresponding key/value pairs to the template. For structured parameters such as collections or objects, verify the data type Mustache receives and how the template renders it into valid JSON.

### Optional Conditions in Mustache

Mustache supports sections to include part of a template only when a parameter has a value. Example:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "title": "{{title}}"
          }
        }
      ]
      {{#category}},
      "filter": [
        {
          "term": {
            "category": "{{category}}"
          }
        }
      ]
      {{/category}}
    }
  }
}
```

The `{{#category}} ... {{/category}}` section renders only when the `category` parameter has an appropriate value. Verify the rendered JSON for both cases—with and without the optional parameter. Commas and braces must be placed so that both branches yield valid JSON.

For complex conditions, multiple collections, or nested structures, write dedicated tests for the template and parameter combinations. Avoid creating a template with so many branches that it becomes hard to read and verify.

## 6. Pagination and Sorting in Search Templates

A search template sends the entire search body according to the stored template definition. Note: even though `SearchTemplateQuery` implements the `Query` interface, not every generic query property is applied automatically. Spring Data documentation notes that `Pageable` and `Sort` set on `SearchTemplateQuery` may be ignored; corresponding values must be placed in the stored template and passed as parameters.

Example template with `from`, `size`, and sort:

```json
{
  "query": {
    "match": {
      "title": "{{title}}"
    }
  },
  "from": {{from}},
  "size": {{size}},
  "sort": [
    {
      "published_at": {
        "order": "{{sortDirection}}"
      }
    }
  ]
}
```

With the Repository annotation, you can declare pagination values as method parameters so the template receives them:

```java
public interface BookRepository
        extends ElasticsearchRepository<Book, String> {

    @SearchTemplateQuery(id = "book-by-title-page")
    SearchHits<Book> findByTitle(String title, int from, int size);
}
```

When invoked:

```java
int page = 0;
int pageSize = 20;
int from = page * pageSize;

SearchHits<Book> hits =
        bookRepository.findByTitle("Spring Data", from, pageSize);
```

The template receives `title`, `from`, and `size`. This makes the parameters required by the template explicit in the method contract.

If you want your service API to accept `Pageable`, use a custom repository implementation to convert `pageable.getOffset()` and `pageable.getPageSize()` into template params. Example:

```java
interface BookSearchRepository {
    SearchPage<Book> searchByTitle(String title, Pageable pageable);
}
```

```java
class BookSearchRepositoryImpl implements BookSearchRepository {

    private final ElasticsearchOperations operations;

    BookSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchPage<Book> searchByTitle(String title, Pageable pageable) {
        SearchTemplateQuery query = SearchTemplateQuery.builder()
                .withId("book-by-title-page")
                .withParams(Map.of(
                        "title", title,
                        "from", pageable.getOffset(),
                        "size", pageable.getPageSize()
                ))
                .build();

        SearchHits<Book> searchHits = operations.search(query, Book.class);
        return SearchHitSupport.searchPageFor(searchHits, pageable);
    }
}
```

In this custom repository example, the `book-by-title-page` template must include `from` and `size` placeholders. If dynamic sorting is needed, pass an allowlisted value and express it within the structure supported by the template; never concatenate arbitrary client sort strings into JSON.

## 7. Using `SearchTemplateQuery` in a Custom Repository

If your project uses Spring Data Elasticsearch 5.1–5.4 or needs to build the parameter map manually, you can use the query object directly instead of the annotation.

Example:

```java
import java.util.Map;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.SearchTemplateQuery;

public class BookSearchRepositoryImpl implements BookSearchRepository {

    private final ElasticsearchOperations operations;

    public BookSearchRepositoryImpl(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @Override
    public SearchHits<Book> searchByTitle(String title) {
        SearchTemplateQuery query = SearchTemplateQuery.builder()
                .withId("book-by-title")
                .withParams(Map.of("title", title))
                .build();

        return operations.search(query, Book.class);
    }
}
```

Here:

- `withId(...)` selects the stored script.
- `withParams(...)` passes an explicit parameter map.
- `operations.search(...)` executes the template and maps results to `Book`.

The query builder also provides `withSource(...)` in supported versions if you need to pass template source instead of just an ID. However, for centrally managed templates on the cluster, prefer IDs and stored scripts so versioning, permissions, and deployment stay easy to control.

## 8. Comparing `@SearchTemplateQuery` with Other Query Approaches

| Query Approach | Where Query Is Defined | Parameter Passing | When Suitable |
|---|---|---|---|
| Derived query method | Repository method name | Method parameters by order/property | Simple conditions easily expressed by method name. |
| `@Query` | JSON Query DSL in annotation | `?0`, `?1` placeholders or SpEL | Fixed, concise queries used only in a single Repository. |
| `CriteriaQuery` | Java Criteria API | Java objects and conditions chained in code | Dynamic search forms or many optional conditions. |
| `NativeQuery` | Elasticsearch Java API Client Query DSL | Typed Java builders | Complex queries requiring native Elasticsearch features. |
| `@SearchTemplateQuery` | Stored Mustache template on cluster | Method parameter names as key/value | Reusable queries managed independently from code. |
| `SearchTemplateQuery` | Stored template or source via query builder | `Map<String, Object>` | Custom repositories needing an explicit parameter map or pre-5.5 compatibility. |

Do not adopt Search Templates solely because it is a newer API. If a query is simple and used in only one place, a derived query or `@Query` may be easier to maintain. Search Templates excel when the same query is shared in multiple places, needs separation from code, or requires centralized management on the cluster.

## 9. Limitations and Caveats

### The Template Must Exist Before Calling the Repository

The annotation only references an ID; it does not register the template automatically. If the stored script has not been created or the ID is wrong, search requests will fail. Deploy templates before rolling out applications that use those IDs.

### Parameter Names Must Match

With the annotation, keys are taken from method parameter names. If a method takes `String searchText` while the template expects `{{title}}`, the parameter is not automatically renamed to `title`. Keep names consistent or use a custom repository with an explicit map.

### No Inline JSON Attribute on the Annotation

`@SearchTemplateQuery` accepts `id`; it does not replace `@Query` for inline JSON. If you want to define the query directly on the Repository method, `@Query` is the separate API for that.

### Pagination and Sorting Must Live Inside the Template

Do not assume `Pageable` or `Sort` will automatically modify the stored script content. Put `from`, `size`, sort, or equivalent placeholders into the template and pass the corresponding values. In a custom repository, building the parameter map from `Pageable` is the clearest way.

### Templates Are Executable Cluster Configuration

Anyone permitted to modify stored scripts can change the application's query behavior. Separate write permissions for stored scripts from runtime search permissions where appropriate. Version templates and test them before updating.

### Mustache Does Not Replace Validation

Templates only render requests. The application must still validate inputs, bound page sizes, allowlist sort fields, and ensure parameters have valid types. Never allow users to pass arbitrary Query DSL fragments or arbitrary field names through public APIs.

## 10. Testing Search Templates

Test both the stored script and the Repository method.

### Verifying Template Registration

In integration tests, create the stored script with `putScript` or provision the template prior to running tests. You can read the template back via `getScript` to confirm the ID and source exist.

### Verifying Rendering with Representative Values

Test scenarios including:

- Ordinary strings.
- Strings with punctuation, quotes, or Unicode characters.
- Optional parameters present and absent.
- Empty and populated collections if the template accepts lists.
- First page and subsequent page pagination values.
- Sorting across allowlisted choices.

Ensure the rendered template produces valid Query DSL and does not alter query semantics unexpectedly.

### Testing the Repository Method

Conceptual test example:

```java
@Test
void searchTemplateShouldFindBooksByTitle() {
    // Arrange: register the stored template and index sample Book documents.
    // Act: call bookRepository.findByTitle("Spring Data").
    // Assert: results contain the expected Book documents.
}
```

Tests must run against the exact Spring Data Elasticsearch version you use. In particular, verify parameter name binding; if values fail to arrive properly, inspect parameter name metadata and template placeholders.

### Testing Template Updates

If a template has multiple consumers, run regression tests across queries using that ID before updating a shared stored script. You can use versioned IDs such as `book-by-title-v1` and `book-by-title-v2`, then switch Repository methods to the new ID in a controlled release.

## 11. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Cannot import `@SearchTemplateQuery` | Spring Data Elasticsearch version is lower than 5.5. | Upgrade to 5.5+ or use `SearchTemplateQuery` in a custom repository (5.1+). |
| Template not found | Stored script not registered or wrong ID. | Check `putScript`, Stored Scripts API, and the annotation ID. |
| Placeholder receives no value | Method parameter name differs from Mustache placeholder name. | Align method parameter names and template keys; verify compiler parameter metadata. |
| Template renders invalid JSON | Misplaced braces, commas, or incompatible placeholder data type. | Test template across all present/absent parameter combinations. |
| Method runs but returns empty results | Wrong Query DSL in template, unsuitable mapping/analyzer, or bad params. | Inspect stored script, sample data, and mappings. |
| `Pageable` does not change paged results | `from`/`size` not included in the stored template. | Add placeholders and pass offset/size explicitly. |
| Sort is ignored | Template has no sort or `Sort` was set only on query object. | Define sort in the template and pass allowlisted parameters. |
| Build succeeds but parameter names fail to bind at runtime | Parameter name metadata missing or mismatches template key. | Enable `-parameters`, check parameter discovery, or use an explicit map in a custom repository. |
| Using `@Query` expecting a stored script to run | The two annotations use different mechanisms. | Use `@SearchTemplateQuery(id = ...)` for stored templates. |

## 12. Recommended Deployment Workflow

1. **Check version:** confirm whether your Spring Data Elasticsearch version supports the annotation or only the query object.
2. **Design template:** write the Query DSL and required Mustache placeholders.
3. **Register template:** use `ElasticsearchOperations.putScript` or the Stored Scripts API.
4. **Create Repository method:** use `@SearchTemplateQuery(id = "...")` on 5.5+; otherwise create a custom repository with `SearchTemplateQuery` on 5.1+.
5. **Map parameters:** make sure method parameter names match template keys, or construct an explicit `Map` in a custom repository.
6. **Configure pagination/sorting:** add `from`, `size`, and sort into the template and pass validated values.
7. **Test:** verify template existence, valid rendering, accurate query results, and parameter binding.
8. **Deploy in order:** register templates first, then roll out the application calling those templates.
9. **Monitor:** watch for script/search errors, latency, and result shifts after template updates.

## 13. Points to Remember

- `@SearchTemplateQuery` marks a Repository method to execute a stored search template by ID.
- The `@SearchTemplateQuery` annotation was introduced in Spring Data Elasticsearch 5.5; the `SearchTemplateQuery` query object was introduced in 5.1.
- Stored search templates must be registered in Elasticsearch and use the Mustache language.
- `@SearchTemplateQuery` specifies the ID; method parameters are sent as key/value pairs using parameter names.
- Placeholder names such as `{{title}}` must match the `title` parameter name in the Repository method.
- On versions 5.1–5.4, use `SearchTemplateQuery.builder()` in a custom repository and pass a map via `withParams(...)`.
- Templates must include `from`, `size`, and sort if the query requires pagination or sorting; do not assume `Pageable`/`Sort` on the query object will automatically modify the stored script.
- Search Templates fit reusable, independently managed queries; simple queries can use derived methods, `@Query`, or `CriteriaQuery`.
- Verify version, parameter name metadata, rendered JSON, and stored-script permissions before deployment.

`@SearchTemplateQuery` lets Repository methods invoke stored search templates with a concise declaration while Query DSL is managed centrally on Elasticsearch. Verify your Spring Data version, register templates before use, and keep parameter contracts explicit so search stays reusable, testable, and safe to deploy.

## References

- [Spring Data Elasticsearch — Query methods](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories/elasticsearch-repository-queries.html)
- [Spring Data Elasticsearch — Search Template support](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Javadoc — `@SearchTemplateQuery`](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/SearchTemplateQuery.html)
- [Javadoc — `SearchTemplateQuery`](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/SearchTemplateQuery.html)
