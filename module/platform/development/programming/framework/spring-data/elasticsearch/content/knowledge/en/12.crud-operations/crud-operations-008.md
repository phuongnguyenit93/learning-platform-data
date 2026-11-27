# Conditional Deletion and How It Differs from Deleting by ID

Spring Data Elasticsearch supports deleting documents in several ways. When the exact identifier of a document is known, the application can call **deleteById(id)** or **ElasticsearchOperations.delete(id, ...)**. When you need to delete all documents matching a business condition, you can use a conditional delete query via **ElasticsearchOperations.delete(Query, ...)**.

These two deletion approaches differ in scope, how Elasticsearch locates documents, and level of control. Deleting by ID targets a specific document. Conditional deletion executes a query on the index and deletes the matching documents. If the condition is too broad or the mapping is wrong, a query-based delete can affect a large number of documents.

This lesson uses a **products** index example, where each document has an ID, SKU, category, status, price, and creation timestamp. We will explore deleting by ID, deleting multiple IDs, conditional deletion with CriteriaQuery, previewing scope before deletion, and handling concurrent updates.

## 1. Two Deletion Approaches Solve Two Different Needs

Suppose the **products** index contains these documents:

~~~json
[
  {
    "id": "p-1001",
    "sku": "KB-1001",
    "category": "accessories",
    "status": "ACTIVE",
    "price": 89.5
  },
  {
    "id": "p-1002",
    "sku": "MS-1002",
    "category": "accessories",
    "status": "DISCONTINUED",
    "price": 29.0
  },
  {
    "id": "p-1003",
    "sku": "HD-1003",
    "category": "storage",
    "status": "DISCONTINUED",
    "price": 59.0
  }
]
~~~

If you need to delete the product with ID **p-1002**, delete by ID. If you need to delete all products with status **DISCONTINUED**, use conditional deletion.

| Criterion | Delete by ID | Conditional delete |
|---|---|---|
| Input | Single ID or collection of IDs | A query describing the condition |
| Scope | Documents with the specified IDs | All documents matching the query |
| How documents are identified | Direct identifier | Elasticsearch runs a search based on the criteria |
| Best suited for | Deleting an already identified document | Cleaning up data by status, time, category, or business criteria |
| Common risk | Passing the wrong ID | Overly broad condition or incorrect query |
| Commonly used APIs | **deleteById**, **deleteAllById**, **delete(id, ...)** | **delete(Query, ...)** or version-supported query methods |

Do not use a conditional delete query just to delete a single document whose ID is already known. Conversely, do not pull all matching documents into the application and loop over IDs to delete them one by one if Elasticsearch can execute delete-by-query directly and business rules allow it.

## 2. Deleting One Document by ID via Repository

When the ID is known, the simplest approach is **deleteById**:

~~~java
productRepository.deleteById("p-1002");
~~~

This method deletes the document with that ID in the index managed by the repository. It does not require building a query on business fields like category or status.

You can check existence before deleting:

~~~java
String productId = "p-1002";

if (productRepository.existsById(productId)) {
    productRepository.deleteById(productId);
}
~~~

Checking beforehand is only useful when business logic must distinguish whether the document existed. It adds an extra query and does not guarantee the document still exists at the moment the delete executes. Another process could delete the document right after the check.

If you do not need separate handling for non-existent documents, calling **deleteById** directly is cleaner.

### Deleting a Loaded Entity

You can delete an object already retrieved from the repository:

~~~java
Product product = productRepository.findById("p-1002")
        .orElseThrow(() -> new ProductNotFoundException("p-1002"));

productRepository.delete(product);
~~~

The repository uses the entity's identifier to determine which document to delete. If you already have the ID, there is no need to load the entire entity before deleting.

## 3. Deleting Multiple Documents by a List of IDs

If you have a list of IDs to delete, use **deleteAllById**:

~~~java
List<String> ids = List.of("p-1002", "p-1003", "p-1010");

productRepository.deleteAllById(ids);
~~~

This fits when the ID list comes from another business operation, such as an administrator selecting several products in a UI and requesting deletion.

You can use **deleteAll(Iterable<T>)** if you already have the entities:

~~~java
List<Product> products = loadProductsSelectedForDeletion();

productRepository.deleteAll(products);
~~~

Do not load full entities just to delete them if the application already has the IDs. A list of IDs is sufficient to identify the target documents.

Also distinguish:

- **deleteAllById(ids)** deletes documents whose IDs are in the list.
- **deleteAll(entities)** deletes the passed entities based on their identifiers.
- **deleteAll()** deletes every document within the repository's scope.

**deleteAll()** is not a conditional delete method. Use it only when business requirements genuinely call for emptying the index or dataset managed by the repository.

## 4. Conditional Deletion with ElasticsearchOperations

When deletion criteria are based on field values, you can construct a Query and pass it to **ElasticsearchOperations.delete(...)**.

For example, deleting products with status **DISCONTINUED**:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductCleanupService {

    private final ElasticsearchOperations operations;

    public ProductCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void deleteDiscontinuedProducts() {
        Criteria criteria = new Criteria("status").is("DISCONTINUED");
        Query query = new CriteriaQuery(criteria);

        IndexCoordinates index = IndexCoordinates.of("products");

        var response = operations.delete(query, Product.class, index);
    }
}
~~~

In this example:

1. **Criteria** describes the condition on the **status** field.
2. **CriteriaQuery** wraps the condition into a query executable by Spring Data Elasticsearch.
3. **IndexCoordinates.of("products")** specifies the target index.
4. **operations.delete(query, Product.class, index)** deletes documents matching the condition.
5. The return value is the delete-by-query response; its exact structure and accessors depend on the Spring Data Elasticsearch version.

This runs as a query-based delete on Elasticsearch. The application does not have to fetch each Product and call **delete(product)** individually.

### Selecting the Right Target Index

If the document class declares **@Document(indexName = "products")**, some overloads can use the entity's metadata to resolve the index:

~~~java
var response = operations.delete(query, Product.class);
~~~

When the application uses aliases or versioned indices, pass **IndexCoordinates** explicitly to control the scope:

~~~java
IndexCoordinates index = IndexCoordinates.of("products-current");
var response = operations.delete(query, Product.class, index);
~~~

Before using an overload, check the **ElasticsearchOperations** method signatures in your project's library version. APIs can vary across Spring Data Elasticsearch generations.

## 5. Combining Multiple Delete Conditions

Delete criteria can be based on one or more fields. For example, deleting only discontinued products in the clearance category:

~~~java
Criteria criteria = new Criteria("status").is("DISCONTINUED")
        .and("category").is("clearance");

Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Compound conditions narrow the deletion scope. Be explicit about whether conditions combine with AND or OR logic, because changing the boolean logic can dramatically increase the number of matched documents.

For instance, with AND logic:

~~~text
status = DISCONTINUED
        AND
category = clearance
~~~

Only documents satisfying both conditions are selected.

With OR logic:

~~~text
status = DISCONTINUED
        OR
category = clearance
~~~

Documents satisfying either condition can be deleted. When using OR, the scope is usually wider; inspect the generated query carefully.

The Criteria API offers operators such as **is**, **isNot**, **greaterThan**, **lessThan**, **between**, **in**, and combinators. Exact names and support depend on the version. For complex queries, you can use **NativeQuery** to express Elasticsearch Query DSL directly.

## 6. Deleting by Time Range

A common scenario is purging documents older than a timestamp, such as expired temporary products or log documents past their retention period.

Suppose the document class has an **expiresAt** date field. You can build a query:

~~~java
import java.time.Instant;

Instant cutoff = Instant.now();

Criteria criteria = new Criteria("expiresAt").lessThan(cutoff);
Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

The query selects documents whose **expiresAt** is earlier than the current timestamp.

When deleting by time, note:

- The field must be mapped as **date**, not arbitrary text.
- Cutoff timestamps must follow the same timezone convention, typically UTC.
- Decide whether documents exactly at the cutoff timestamp should be deleted or only those strictly earlier.
- If documents can have a null or missing date field, decide explicitly whether they belong in the cleanup scope.
- Do not rely on the local clock of the application host if the system requires a unified, controlled time source.

## 7. Deleting by Price Range or Numeric Values

Queries can also filter on numeric fields. For example, deleting test products priced at 0:

~~~java
Criteria criteria = new Criteria("price").is(0.0);
Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Or deleting records with negative prices caused by corrupt data:

~~~java
Criteria criteria = new Criteria("price").lessThan(0.0);
Query query = new CriteriaQuery(criteria);

var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Range conditions work properly only when the field is mapped to an appropriate numeric type. If the price field is stored as text, numeric comparisons may not behave as expected.

In production systems, deleting erroneous data should typically be paired with audit trails or exporting affected records for investigation beforehand. Especially for financial, audit, or critical business data, retention policies may require marking a status flag instead of physical deletion.

## 8. How Query Deletion and deleteById Differ at the Elasticsearch Layer

When calling **deleteById**, Elasticsearch receives a request to delete a document by identifier. The application already knows the exact target document.

When calling delete-by-query, Elasticsearch executes a query on the index to find matching documents and then issues delete operations for the result set. This mechanism fits when the application does not have each document's ID ahead of time.

| Aspect | Delete by ID | Delete-by-query |
|---|---|---|
| How documents are found | By **_id** | Executes a query on the index |
| Document count | Typically one per ID; can call for multiple IDs | Can delete many matching documents |
| Search work | No search on business fields needed | Must find documents matching the query |
| Blast radius | Bounded by input IDs | Depends entirely on query criteria |
| Input | ID | Criteria, Query DSL, or Query |
| Typical use case | User deletes one specific product | Purging products by status or age |
| Primary risk | Wrong ID or deleting the wrong specific document | Missing filter, wrong mapping, or matching too many documents |

Delete-by-query does not delete the index. It deletes only documents matching the query in the specified index. Mappings, settings, aliases, and non-matching documents remain intact.

## 9. Checking the Count Before Deleting

For conditional delete operations, include a scope-preview step. You can call **ElasticsearchOperations.count(...)** with the same query:

~~~java
Criteria criteria = new Criteria("status").is("DISCONTINUED");
Query query = new CriteriaQuery(criteria);
IndexCoordinates index = IndexCoordinates.of("products");

long matchedCount = operations.count(query, Product.class, index);

if (matchedCount > 0) {
    var response = operations.delete(query, Product.class, index);
}
~~~

This tells you how many documents currently match the condition before deleting. You can log this count or show it on an admin confirmation screen.

However, count and delete are two separate operations. Data can change between the count and the delete. Thus, the preview count is not a transactional lock and does not guarantee the exact number of deleted documents will equal the counted number.

When business rules require confirmation before deletion, display clearly:

- Target index or alias.
- Full query condition.
- Expected number of affected documents.
- Initiating user and timestamp.
- Retention policy or recovery options.

Never execute delete-by-query if the input criteria are empty or unvalidated. An unconstrained query can effectively delete every document in the index.

## 10. Checking Mappings Before Writing Criteria

Queries must match the field mappings. Example:

~~~json
{
  "properties": {
    "status": {
      "type": "keyword"
    },
    "category": {
      "type": "keyword"
    },
    "name": {
      "type": "text"
    },
    "price": {
      "type": "double"
    },
    "expiresAt": {
      "type": "date"
    }
  }
}
~~~

Notes:

- **status** and **category** are keyword fields, suitable for exact matching conditions.
- **name** is text, suitable for full-text queries. When deleting by name content, determine whether you need a match query or an exact match on a keyword multi-field.
- **price** is double, suitable for numeric range conditions.
- **expiresAt** is date, suitable for before/after timestamp conditions.

Using **term** on a text field can yield unexpected results because the content has been processed by an analyzer. When exact matching is required, use a keyword field or keyword multi-field.

## 11. How Delete-by-Query Handles Concurrent Updates

Elasticsearch delete-by-query searches against a point-in-time snapshot of the index and deletes the found documents. While the operation is running, another process may update or delete some of those documents.

As a result, version conflicts can occur. For example:

1. Delete-by-query finds a product with status DISCONTINUED.
2. Another process updates that product to ACTIVE.
3. Delete-by-query attempts to delete the document version it found.
4. Elasticsearch detects that the document changed and may report a version conflict.

Delete-by-query is not an index-wide transaction. There is no automatic rollback to restore deleted documents if part of the operation encounters errors.

For large administrative operations, decide how conflicts should be handled:

- Abort and investigate if conflicts indicate unexpected concurrent data modifications.
- Allow proceeding past conflicts if business rules permit skipping modified documents, while recording conflict counts.
- Pause or coordinate related write streams during cleanup if strict consistency is required.

Elasticsearch's Delete By Query API offers options like **conflicts**, **requests_per_second**, **slices**, and asynchronous task execution depending on version. Spring Data Elasticsearch does not necessarily expose all of these options through every overload. When fine-grained control is needed, use the Elasticsearch Java API Client compatible with your cluster version.

## 12. Return Values and Errors from Delete-by-Query

Unlike **deleteById**, a delete-by-query operation can return a response containing information about deleted document counts, batch counts, version conflicts, and failures.

Example:

~~~java
var response = operations.delete(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Do not assume that returning without throwing an exception means every document was deleted cleanly. Inspect the response structure and log according to your version's API. Some operations can complete partially while still returning failure details.

When processing the response, track:

- Number of deleted documents.
- Number of version conflicts.
- Batch or document-level failures.
- Task status if executed asynchronously.
- Execution duration and processing rate.

If the client disconnects after sending the request, do not immediately resend without checking status. The initial request may have partially or fully executed even though the client did not receive the response. Check the index, tasks, or logs before deciding to re-run.

## 13. Conditional Deletion Does Not Remove Data from Search Immediately

Elasticsearch is a near real-time system. After deletion, changes may not appear immediately in search results until the index refreshes.

If a business workflow must verify search results immediately after deletion, use a refresh mechanism appropriate for your version's API or call refresh deliberately:

~~~java
IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

indexOperations.refresh();
~~~

Avoid refreshing after every delete operation in high-load environments. Frequent refreshes can hurt indexing performance. In normal application flows, rely on the default refresh interval and trigger explicit refreshes only when clearly required by business logic.

Also distinguish document deletion from index deletion:

- **deleteById** deletes one document by ID.
- **delete(Query, ...)** deletes documents matching a query.
- **IndexOperations.delete()** deletes the entire physical index, including documents, mappings, and settings.

These three operations have vastly different blast radii.

## 14. Encapsulating Conditional Deletion in a Service

Place conditional delete logic inside a service to centralize business rules, target index resolution, and input validation before calling Elasticsearch.

Example:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductCleanupService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public ProductCleanupService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public long countDiscontinuedProducts() {
        Query query = discontinuedProductsQuery();
        return operations.count(query, Product.class, PRODUCTS);
    }

    public void deleteDiscontinuedProducts() {
        Query query = discontinuedProductsQuery();

        long count = operations.count(query, Product.class, PRODUCTS);
        if (count == 0) {
            return;
        }

        var response = operations.delete(query, Product.class, PRODUCTS);

        // Log the response according to the API of the version in use.
    }

    private Query discontinuedProductsQuery() {
        Criteria criteria = new Criteria("status").is("DISCONTINUED");
        return new CriteriaQuery(criteria);
    }
}
~~~

The service uses a single method to build the query, keeping the preview condition and delete condition consistent in code. Still, count and delete remain two separate requests, so data can change between the two steps.

In production systems, you can parameterize category, cutoff time, or status, provided every parameter is validated before constructing the query. Never allow callers to pass an empty query or an unrestricted full-index delete condition unless business rules explicitly allow it.

## 15. Should You Use Derived Delete Queries in Repositories?

Spring Data includes query derivation from method names. Some versions and repository types support property-based delete methods, such as **deleteByStatus(...)**. However, exact support and return types must be verified against the Spring Data Elasticsearch version you use.

If a project uses a derived delete query:

~~~java
void deleteByStatus(String status);
~~~

Check the version documentation and actual runtime behavior of the query method, especially when you need the count of deleted documents or partial failure handling.

When you need to make the query, target index, preview count, or response metadata explicit, **ElasticsearchOperations.delete(Query, ...)** is generally easier to control.

Do not pick a derived delete method solely for brevity. Conditional deletion has broad data impact, so readers of the code should easily see the scope of affected documents.

## 16. Physical Deletion vs. Status Marking

Documents should not always be physically deleted. Business data often needs history retained for auditing, recovery, or reporting.

An alternative is updating a status instead of deleting:

~~~java
Product product = productRepository.findById(productId)
        .orElseThrow(() -> new ProductNotFoundException(productId));

product.setStatus("ARCHIVED");
productRepository.save(product);
~~~

Normal queries then filter out the ARCHIVED status. The data stays in the index and remains inspectable by administrative jobs.

Choose between physical deletion and status marking based on:

- Data retention policies.
- Audit requirements.
- Recovery needs.
- Storage costs.
- Privacy and data-erasure requirements.
- Impact on reporting and downstream integrated systems.

If business rules mandate physical deletion, ensure all replicas or synchronization pipelines also process the deletion per the system's data policy.

## 17. Common Errors in Conditional Deletion

| Symptom | Possible cause | Resolution |
|---|---|---|
| More documents deleted than expected | Query missing a condition or unintended OR logic | Inspect the query and count matching documents before deleting |
| Documents not deleted | Wrong field name, mapping type, or condition | Inspect mappings and test the query using the search API |
| Delete by ID finds nothing | Wrong ID or document already deleted | Verify the ID and define the contract when absent |
| Delete-by-query reports version conflict | Documents updated during the operation | Define a conflict policy and coordinate write flows |
| Some documents were not deleted | Batch errors or operation interrupted | Inspect response failures and re-check remaining documents |
| Delete succeeds but search still returns documents | Index has not refreshed yet | Wait for refresh or refresh deliberately if required |
| Client timeout | Long-running operation or lost response | Check actual index/task status before re-running |
| Needed data accidentally deleted | No backup or event log | Define backup, snapshot, and retention policies before deleting |
| Entire index accidentally deleted | Misused **deleteAll()** or **IndexOperations.delete()** | Distinguish document deletion from index deletion; restrict admin permissions |

## 18. Principles for Choosing a Delete API

You can follow these guidelines:

1. Use **deleteById(id)** when you know the exact single document to delete.
2. Use **deleteAllById(ids)** when you have a specific list of IDs.
3. Use **delete(entity)** or **deleteAll(entities)** when you already hold the entities to delete.
4. Use **ElasticsearchOperations.delete(Query, ...)** when you need to delete all documents matching a condition.
5. Use **count(query, ...)** to preview scope for high-impact operations, remembering that count does not lock data.
6. Confirm the exact target index or alias before executing.
7. Check mapping types and query types so conditions match data accurately.
8. Inspect the delete-by-query response, including deleted counts, conflicts, and failures per your version's API.
9. Define how concurrent updates and newly arriving documents during deletion are handled.
10. Use **deleteAll()** or index deletion only when business requirements genuinely call for that scope.

Deleting by ID works best when document identifiers are known and the deletion scope is small and explicit. Conditional deletion fits cleanup jobs by status, category, timestamp, or business rules. In Spring Data Elasticsearch, repositories keep ID-based deletion simple, while **ElasticsearchOperations.delete(Query, ...)** lets you push conditions to Elasticsearch for bulk removal. Before running a query-based delete, identify the index, verify mappings, preview scope, and plan for errors or concurrent updates.
