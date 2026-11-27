# Managing Search Resources and Exception Translation

Spring Data Elasticsearch provides several APIs for working with Elasticsearch beyond repository CRUD methods. Applications can create indices, write mappings, update settings, manage aliases, store search templates, execute queries, and manage the lifecycle of search resources. When these operations fail, Spring Data also provides a mechanism to translate certain Elasticsearch-specific exceptions into Spring's unified exception hierarchy.

These two sets of capabilities help applications manage Elasticsearch in a more structured way:

- Index management and query operations are organized through **ElasticsearchOperations**, **IndexOperations**, and related interfaces.
- Errors from the persistence layer can be translated into **DataAccessException** so services can handle them using Spring's abstraction.

This lesson focuses on choosing the right interface, managing resource lifecycles, using stored search templates, and understanding the limits of exception translation.

## 1. Distinguishing Operations Groups

Spring Data Elasticsearch organizes APIs into functional groups corresponding to Elasticsearch APIs:

| Interface | Responsibility |
| --- | --- |
| IndexOperations | Resource-level index management: create, delete, check existence, settings, mappings, aliases, and index templates |
| DocumentOperations | Save, update, read, and delete documents by ID |
| SearchOperations | Execute searches, counts, multi-search, streams, scroll, and Point in Time |
| ScriptOperations | Store, read, and delete stored scripts/search templates |
| ElasticsearchOperations | High-level API combining document and search operations, while also providing a helper to obtain IndexOperations |

ElasticsearchOperations is not a repository. It is a lower-level abstraction than repositories, suitable when you need flexible queries, index management, or operations not naturally expressed as query methods.

### 1.1. Injecting ElasticsearchOperations

Spring Boot together with the Spring Data Elasticsearch starter typically configures an ElasticsearchOperations bean for the application to use:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

Constructor injection makes it clear that the service depends on the persistence/search API. Do not manually instantiate clients in each service if the application already has a Spring-managed client.

### 1.2. Obtaining IndexOperations by Entity or Index Name

There are two ways to obtain an index management object:

~~~java
IndexOperations byEntity = operations.indexOps(ProductDocument.class);

IndexOperations byIndexName =
    operations.indexOps(IndexCoordinates.of("catalog-products-v2"));
~~~

indexOps(ProductDocument.class) uses the entity's metadata, such as the index name in @Document. indexOps(IndexCoordinates) works with an explicitly specified index name or set of indices. The second approach is useful when managing versioned physical indices, aliases, or resources not tied directly to a single entity.

## 2. Managing Index Lifecycle with IndexOperations

An index is a high-level resource containing mappings, settings, and documents. Creating indices and changing mappings must be managed intentionally, especially in staging and production environments.

### 2.1. Checking and Creating an Index

Suppose the entity is declared as:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // Constructors, getters, and setters
}
~~~

You can create the index together with the mapping generated from annotations:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

createWithMapping() creates the index and the mapping corresponding to the entity's metadata. If you need to separate the two steps, call create() and then putMapping(). For explicit settings and mapping configurations, IndexOperations also provides index creation methods that accept settings and mappings.

Note: obtaining IndexOperations or ElasticsearchOperations does not automatically create the index. When using these APIs directly, the application must invoke the index creation operation. Spring Data repositories have a mechanism to auto-create indices/mappings based on document configuration, but that is repository-specific bootstrap behavior.

### 2.2. Reading Mappings and Settings

After creating an index, you can read back its live configuration:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

Document mapping = indexOperations.getMapping();
Document settings = indexOperations.getSettings();
~~~

Mappings describe how Elasticsearch interprets each field: data types, analyzers, multi-fields, object/nested structures, and dynamic behavior. Settings describe index configuration such as shards, replicas, refresh interval, and storage options.

Do not treat annotations or JSON files in source code as the sole proof of the running configuration. An index may have been created earlier, managed via a template, or modified directly on the cluster. Reading mappings/settings from Elasticsearch verifies the actual state.

### 2.3. Writing Mappings

If an index already exists and needs compatible mapping fields added, you can use:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

indexOperations.putMapping();
~~~

Or generate a mapping from another class:

~~~java
Document mapping =
    operations.indexOps(ProductDocument.class).createMapping();

operations.indexOps(IndexCoordinates.of("catalog-products"))
    .putMapping(mapping);
~~~

Updating mappings has Elasticsearch limitations. You can add new fields or supplement certain supported attributes, but you cannot arbitrarily change the type of an already-indexed field. If incompatible changes are needed, you usually must create a new index and reindex the data.

### 2.4. Deleting an Index

IndexOperations provides an operation to delete an index:

~~~java
IndexOperations indexOperations =
    operations.indexOps(IndexCoordinates.of("catalog-products-test"));

if (indexOperations.exists()) {
    indexOperations.delete();
}
~~~

Deleting an index removes its documents and configuration. Only use this operation on clearly identified resources, such as test indices or old indices after completing a migration. Never pass an index name taken directly from user input to delete.

## 3. Managing Aliases and Index Versions

An alias is a logical name pointing to one or more indices. Applications can use a stable alias while operations teams create new versioned physical indices.

~~~text
catalog-products  (alias)
        |
        v
catalog-products-v2  (current physical index)
~~~

When a schema change is needed, you can create catalog-products-v3, load data, verify it, and switch the alias. The application continues using the catalog-products alias, so index names do not need to change across services.

### 3.1. Creating an Alias

Aliases can be managed via IndexOperations and Spring Data's alias actions API. The Elasticsearch REST API illustrates attaching an alias:

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "catalog-products-v2",
        "alias": "catalog-products",
        "is_write_index": true
      }
    }
  ]
}
~~~

is_write_index designates which index receives write operations when an alias points to multiple indices. Even if an alias points to a single index, establish consistent read/write rules in the application design.

### 3.2. Atomic Alias Switching

Once the new index is ready, you can remove the old link and add the new link in the same aliases request:

~~~http
POST /_aliases
{
  "actions": [
    {
      "remove": {
        "index": "catalog-products-v2",
        "alias": "catalog-products"
      }
    },
    {
      "add": {
        "index": "catalog-products-v3",
        "alias": "catalog-products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Switching the alias in a single request avoids a window where the application references a non-existent alias between two separate operations. Before switching, verify document counts, mappings, queries, and the policy for syncing new writes occurring during migration.

### 3.3. When to Use Aliases?

- Keep index names stable in application code.
- Route read/write traffic to a new index after reindexing.
- Separate read aliases and write aliases when a clear deployment workflow is needed.
- Support rollover or managing multiple time-based indices.

An alias is not a copy of data. It is only a reference name pointing to indices. Deleting an alias does not delete the index, whereas deleting an index invalidates the alias pointing to it.

## 4. Index Templates and Stored Search Templates

These two types of templates have different purposes:

| Template Type | Purpose |
| --- | --- |
| Index template | Applies settings, mappings, and aliases to new indices whose names match a pattern |
| Search template | Stores a parameterized search query for reuse |

Do not confuse search templates with index templates simply because both contain the word template.

### 4.1. Index Templates

Index templates standardize configuration for new indices. Example:

~~~http
PUT /_index_template/catalog-template
{
  "index_patterns": ["catalog-products-*"],
  "priority": 100,
  "template": {
    "settings": {
      "number_of_shards": 3,
      "number_of_replicas": 1,
      "refresh_interval": "1s"
    },
    "mappings": {
      "properties": {
        "sku": {
          "type": "keyword"
        },
        "name": {
          "type": "text"
        }
      }
    }
  }
}
~~~

Templates are applied when creating a new index matching index_patterns. Modifying a template does not automatically update existing indices. Existing indices must be updated via the corresponding APIs or a migration process.

Spring Data Elasticsearch provides index template APIs via IndexOperations in supported versions. When you need newer composable/component template features not covered by the abstraction, use the Elasticsearch Java API Client directly in an infrastructure adapter.

### 4.2. Stored Search Templates

Search templates store Query DSL as Mustache scripts in the cluster. Spring Data provides ScriptOperations through ElasticsearchOperations.

Example storing a template:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.script.Script;

Script script = Script.builder()
    .withId("products-by-name")
    .withLanguage("mustache")
    .withSource("""
        {
          "query": {
            "match": {
              "name": "{{name}}"
            }
          },
          "from": "{{from}}",
          "size": "{{size}}"
        }
        """)
    .build();

operations.putScript(script);
~~~

Placeholders such as {{name}}, {{from}}, and {{size}} are replaced with parameters at execution time. Search template scripts use the Mustache language.

You can read or delete stored scripts using the corresponding methods:

~~~java
operations.getScript("products-by-name");
operations.deleteScript("products-by-name");
~~~

Deleting a script can break search flows still referencing that ID. Deploy template versions and application code in a compatible order.

### 4.3. Executing SearchTemplateQuery

Building a query from a stored template:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.core.query.SearchTemplateQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchTemplateQuery query = SearchTemplateQuery.builder()
    .withId("products-by-name")
    .withParams(Map.of(
        "name", "mechanical keyboard",
        "from", 0,
        "size", 20
    ))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Search templates are useful when complex Query DSL is reused across multiple places or when query definitions should be managed on the cluster side. Input parameters must still be validated in the application.

SearchTemplateQuery does not support every option the same way regular queries do. For instance, Pageable or Sort set on the query object may not be applied; if the template needs pagination or sorting, make those values placeholders in the script.

### 4.4. Using Templates in Repositories

In supported versions, stored templates can be bound to repository methods:

~~~java
import org.springframework.data.elasticsearch.annotations.SearchTemplateQuery;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;
import org.springframework.data.elasticsearch.core.SearchHits;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @SearchTemplateQuery(id = "products-by-name")
    SearchHits<ProductDocument> findByName(String name);
}
~~~

Method parameters are converted into key/value pairs by parameter name to pass into the search template. Verify compiler configuration preserving parameter names and your Spring Data Elasticsearch version before relying on this binding mechanism.

## 5. Managing Long-Lived Search Resources: Scroll and Point in Time

A query returning a large volume of documents may need to be processed incrementally. Elasticsearch supports Scroll and Point in Time (PIT). These are lifecycle-managed resources and must be closed when finished.

### 5.1. Search Stream

Spring Data provides searchForStream to read results incrementally:

~~~java
import org.springframework.data.elasticsearch.core.SearchHitsIterator;
import org.springframework.data.elasticsearch.core.query.Query;

SearchHitsIterator<ProductDocument> stream =
    operations.searchForStream(
        query,
        ProductDocument.class,
        IndexCoordinates.of("catalog-products")
    );

try {
    while (stream.hasNext()) {
        ProductDocument product = stream.next();
        // Process each document
    }
} finally {
    stream.close();
}
~~~

Closing the stream releases client/server scroll resources. Do not keep scroll contexts open longer than necessary or leave unclosed streams open.

### 5.2. Point in Time

PIT creates a stable view of an index over a period of time to support deep pagination or multiple consecutive queries over the same logical snapshot.

Example opening and closing a PIT:

~~~java
import java.time.Duration;

IndexCoordinates index = IndexCoordinates.of("catalog-products");
String pitId = operations.openPointInTime(
    index,
    Duration.ofMinutes(1)
);

try {
    // Build Query with Point In Time and execute search pages.
} finally {
    operations.closePointInTime(pitId);
}
~~~

During PIT pagination, Elasticsearch may return a new PIT ID; continue using the latest ID from the response and close the final ID when done. Keep-alive should cover processing time without being needlessly extended.

Scroll and PIT do not replace each other in every case. Choose the mechanism based on consistency requirements, pagination style, and Elasticsearch version.

## 6. Exception Translation in Spring Data Elasticsearch

The Elasticsearch client can throw proprietary exceptions when requests fail. If every service had to understand client-specific exceptions, application code would become tightly coupled to the storage technology.

Spring Data Elasticsearch provides exception translation to convert certain runtime exceptions into Spring's exception hierarchy in package org.springframework.dao.

The goal is to create a common abstraction for data access errors, similar to how Spring supports JDBC, JPA, or other persistence modules.

### 6.1. DataAccessException

DataAccessException is the root class in Spring's data access exception hierarchy. Subclasses represent different error categories, such as resource access failures, data access API errors, or data integrity issues.

Benefits:

- Services do not need to depend directly on every Elasticsearch client exception class.
- Error handling can be organized by persistence category.
- Preserves the original exception as the cause for logging and investigation.
- Enables standardizing HTTP responses at the web layer without exposing client internals.

Exception translation does not mean every runtime error becomes a DataAccessException. If the translator does not recognize an exception, it can return null to indicate that the exception is outside the translation scope.

### 6.2. ElasticsearchExceptionTranslator

For the Elasticsearch Java API Client, Spring Data Elasticsearch provides:

~~~java
org.springframework.data.elasticsearch.client.elc.ElasticsearchExceptionTranslator
~~~

This class implements PersistenceExceptionTranslator. The translateExceptionIfPossible(RuntimeException) method attempts to translate an exception into a DataAccessException. If no suitable mapping exists, the result is null.

The modern implementation constructor accepts JsonpMapper because some exceptions from the Java API Client require a mapper to interpret response bodies. Translator APIs and packages differ between client generations. In modern versions using the Java API Client, do not copy legacy examples based on the High Level REST Client.

Spring Data Elasticsearch notes that default Operations implementations support resource management and exception translation. Therefore, when using Spring-configured ElasticsearchOperations or repositories, applications generally do not need to invoke the translator manually for each operation.

### 6.3. Spring's PersistenceExceptionTranslator Mechanism

Spring defines the PersistenceExceptionTranslator interface so persistence modules can provide translation from technology-specific exceptions to standard exceptions.

For DAO beans annotated with @Repository, PersistenceExceptionTranslationPostProcessor can apply an advisor to translate matching exceptions when calls pass through those beans. Spring Data also integrates exception translation directly into its persistence infrastructure.

General flow:

~~~text
Service
   |
   v
Repository / ElasticsearchOperations
   |
   v
Elasticsearch Java API Client
   |
   v
Exception from client or cluster
   |
   v
ElasticsearchExceptionTranslator
   |
   v
Spring DataAccessException hierarchy
   |
   v
Service / API exception handler
~~~

If an application calls the low-level client directly outside Spring Data, do not assume those calls automatically undergo exception translation like repository or template calls. A dedicated translator or adapter may be needed to keep error contracts consistent.

## 7. Identifying and Handling Errors by Category

When interacting with Elasticsearch, errors usually stem from one of the following categories:

| Error Category | Example Causes | Handling Approach |
| --- | --- | --- |
| Connection and resources | Cluster unreachable, timeout, node unavailable | Check network, endpoints, TLS, credentials, cluster health; consider bounded retries |
| Invalid request or query | Wrong field type, malformed Query DSL, missing parameter | Fix query/mapping or input validation; do not retry blindly |
| Mapping and schema | Writing string to numeric field, incompatible type change | Check mapping and data; use index migration if needed |
| Missing resource | Missing index, alias, or stored script | Check resource lifecycle and deployment order |
| Data conflict | Version conflict or unmet write condition | Re-read state, apply optimistic concurrency, or apply business rules |
| Authentication/authorization error | Invalid credentials or missing privileges | Check secrets and granted roles/privileges |

The exception translator standardizes exception types but does not replace cause classification. The same DataAccessException may require different actions depending on its cause, HTTP status, Elasticsearch details, and business context.

### 7.1. Preserving the Cause

When wrapping exceptions into business exceptions, retain the original exception as the cause:

~~~java
public class SearchUnavailableException extends RuntimeException {

    public SearchUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Example service translating a data access error into an application error:

~~~java
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchFacade {

    private final ProductSearchService searchService;

    public ProductSearchFacade(ProductSearchService searchService) {
        this.searchService = searchService;
    }

    public SearchResult search(String text) {
        try {
            return searchService.search(text);
        } catch (DataAccessResourceFailureException ex) {
            throw new SearchUnavailableException(
                "Search service is temporarily unavailable",
                ex
            );
        }
    }
}
~~~

The example above only illustrates preserving the cause and translating at the application boundary. Specific thrown exception classes depend on the translator and actual failure type; do not assume every Elasticsearch error is a DataAccessResourceFailureException.

### 7.2. Do Not Catch All Exceptions and Return Empty Results

A common anti-pattern:

~~~java
try {
    return repository.findBySku(sku);
} catch (Exception ex) {
    return Optional.empty();
}
~~~

This code turns connection errors, mapping errors, programming bugs, and query errors into a "not found" result. Callers cannot distinguish a non-existent product from a failing search cluster.

Let unexpected errors propagate or translate them into appropriate business exceptions. Only return empty results when the query genuinely completes successfully with no matching documents.

### 7.3. Retries Must Be Conditional

Not all data access errors are retryable:

- Timeouts or transient network failures can be retried with backoff and a maximum retry count.
- Validation errors or invalid Query DSL will keep failing if retried.
- Data writes must consider idempotency and version conditions before retrying.
- Never retry infinitely, as it can overload the cluster while it is recovering.

If using Spring Retry or an application retry mechanism, configure by specific exception type, max attempts, backoff, and overall timeout.

## 8. Standardizing Exceptions at the API Layer

The web layer should not return stack traces, raw Elasticsearch responses, or cluster internals to clients. You can use @RestControllerAdvice to turn application exceptions into consistent responses.

Example:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(SearchUnavailableException.class)
    public ResponseEntity<ApiError> handleSearchUnavailable(
            SearchUnavailableException ex) {

        ApiError error = new ApiError(
            "SEARCH_UNAVAILABLE",
            "Search is temporarily unavailable"
        );

        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(error);
    }
}
~~~

ApiError is an application-defined DTO. Do not map every DataAccessException to HTTP 503. A bad query or mapping error sent by the application may be a server error; invalid input data may require a different response; only transient resource or cluster failures are suited for 503.

Internal logs can capture the original exception alongside a correlation ID, while client responses should contain only enough information for communication-layer handling.

## 9. Handling Errors During Resource Operations

Index and template management operations usually occur during startup, migration, or deployment. Certain scenarios need dedicated handling:

**Index already exists.** Check with exists() before creating, or let migrations manage state. If multiple instances run the creation step concurrently, a race condition can still occur between checking and creating.

**Incompatible mapping.** Do not attempt to write a new mapping if the change requires altering a field's type. Create a new versioned index, reindex, and switch the alias.

**Alias does not exist or points to the wrong index.** Inspect the aliases API and target index before switching traffic. Keep a clear rollback step.

**Search template not yet stored.** Deploy stored scripts before deploying code referencing that template ID. When updating a template, you can use a new versioned ID for safe rollout.

**PIT/scroll left unclosed.** Use finally or try-with-resources where the API supports it to release resources even when document processing throws an exception.

**Index deletion fails due to insufficient permissions.** Verify roles/privileges and deployment processes; do not retry automated deletion indefinitely.

## 10. Fitting Resource Management into Application Architecture

Controllers should not directly create indices, switch aliases, or delete stored scripts. These operations belong to infrastructure and deployment lifecycles.

One way to organize:

~~~text
com.example.catalog
├── product
│   ├── api
│   ├── application
│   └── infrastructure
│       └── elasticsearch
│           ├── ProductRepository.java
│           ├── ProductSearchAdapter.java
│           └── ProductIndexManager.java
├── search
│   ├── application
│   └── infrastructure
│       └── SearchTemplateManager.java
└── shared
    └── error
        ├── SearchUnavailableException.java
        └── ApiExceptionHandler.java
~~~

Responsibilities can be divided as follows:

- ProductRepository: CRUD and simple query methods.
- ProductSearchAdapter: complex queries using ElasticsearchOperations.
- ProductIndexManager: create/verify indices and mappings in bootstrap or migration workflows.
- SearchTemplateManager: install, update, and delete stored search templates.
- SearchUnavailableException: business exception for the application layer to express failures.
- ApiExceptionHandler: translates application exceptions into HTTP responses.

In production, consider separating index administration privileges from document read/write privileges. The runtime application typically only needs data and search permissions; deployment/migration steps can use credentials with index/template/alias management privileges.

## 11. Recommended Deployment and Operations Workflow

A search resource management workflow can follow these steps:

1. Declare document metadata, mappings, and required settings.
2. Define physical indices, read/write aliases, and versioning rules.
3. Create or update index templates for new indices if the cluster uses templates.
4. Create new indices via migrations or IndexOperations, then verify mappings/settings.
5. Ingest or reindex data and verify document counts, queries, and aggregations.
6. Switch aliases once the new index is ready.
7. Deploy stored search templates before code using the new template IDs.
8. Use ElasticsearchOperations for specialized queries, PIT, or streams; always close long-lived resources.
9. Monitor cluster health, query latency, indexing failures, and translated exceptions.
10. Delete old resources after a verification period and per retention policies.
11. Standardize exceptions at the application and API boundaries; keep causes for logging.
12. Only retry transient errors and operations that are safe to retry.

## 12. Common Pitfalls

**Thinking IndexOperations creates indices automatically.** Obtaining an IndexOperations object sends no requests. You must call create(), createWithMapping(), or the corresponding operation.

**Using IndexOperations for all document operations.** IndexOperations manages index resources. Use DocumentOperations or ElasticsearchOperations for saving/reading/deleting documents.

**Confusing index templates with search templates.** Index templates configure new indices; search templates store parameterized queries. The two resources do not replace each other.

**Updating an index template and expecting existing indices to update settings.** Templates apply only when new indices are created. Existing indices need separate updates.

**Switching aliases before reindexing completes.** Users may read incomplete data. Verify data and queries before switching.

**Deleting an index using a client-supplied name.** This can delete the wrong resource. Use an allowlist or mapping between business concepts and managed index names.

**Failing to close streams or PITs.** Long-lived search resources put pressure on the cluster. Always manage lifecycles with finally or proper closing mechanisms.

**Assuming every Elasticsearch exception is translated to DataAccessException.** Translators only convert recognized exceptions; exceptions from user code may pass through unchanged.

**Catching every DataAccessException and retrying.** Mapping, query, or validation errors will not resolve on their own. Classify by cause and idempotency.

**Returning raw exceptions to API clients.** That can leak index names, queries, endpoints, or cluster internals. Convert to application errors with minimal details.

## 13. References

- [Spring Data Elasticsearch - Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): distinguishing IndexOperations, DocumentOperations, SearchOperations, and ElasticsearchOperations; query APIs.
- [Spring Data Elasticsearch - Miscellaneous Operation Support](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html): index settings, mappings, stored search templates, Scroll, and Point in Time.
- [Spring Data Elasticsearch API - IndexOperations](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/IndexOperations.html): index management API.
- [Spring Data Elasticsearch API - ElasticsearchExceptionTranslator](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchExceptionTranslator.html): exception translator for Elasticsearch Java API Client.
- [Spring Framework - DAO support](https://docs.spring.io/spring-framework/reference/data-access/dao.html): data access exception hierarchy and exception translation.

APIs, packages, and behaviors may vary across Spring Data Elasticsearch and Elasticsearch Java Client versions. When implementing, consult the Javadoc and documentation for your project's exact dependency version.
