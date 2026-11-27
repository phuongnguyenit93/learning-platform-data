# AfterLoadCallback and AfterConvertCallback When Reading

When Spring Data Elasticsearch reads a document, the data passes through several steps before becoming a Java object used by a service. Sometimes the application needs to normalize raw data before mapping; other times it needs to adjust the entity after the converter has created the object. The two callbacks **AfterLoadCallback** and **AfterConvertCallback** serve those two distinct points in the read flow.

**AfterLoadCallback** is tied to the stage where the document has been retrieved from Elasticsearch. **AfterConvertCallback** is tied to the stage after the entity has been converted from the document. Choosing the right callback places data processing in the proper layer, keeps mapping understandable, and avoids stuffing read-time logic into repositories or services.

This lesson explains each callback's position in the read lifecycle, how to register callbacks in Spring, how to modify the document or entity, execution order, scope of application, combining with auditing, performance considerations, and testing.

## 1. Document Read Flow in Spring Data Elasticsearch

When calling a repository or `ElasticsearchOperations` to read an entity, Spring Data converts the Elasticsearch response into an intermediate document and then converts that document into the target Java type.

High-level flow:

~~~text
Repository / ElasticsearchOperations
              |
              v
       Elasticsearch search/get
              |
              v
       Elasticsearch response
              |
              v
       Spring Data Document
              |
              v
       AfterLoadCallback
              |
              v
       MappingElasticsearchConverter
              |
              v
        Domain entity
              |
              v
      AfterConvertCallback
              |
              v
      SearchHit / entity result
              |
              v
          Application
~~~

Internal step names and details can differ across read APIs and Spring Data Elasticsearch versions. The key point is that callbacks are tied to the lifecycle managed by Spring Data; they are not arbitrary interceptors for every HTTP operation sent to Elasticsearch.

The two callbacks sit at different stages:

- **AfterLoadCallback** fits processing a newly loaded document before the application uses the mapped entity.
- **AfterConvertCallback** fits processing a Java object after the converter has created the entity.

A read operation can pass through both callbacks if the API and version in use support them in that flow.

## 2. When Do You Need Post-Read Callbacks?

Suppose an index holds product data from multiple application versions. Some older documents use a `productName` field, whereas the current Java model uses `name`. Or the system needs to normalize a legacy value before the converter maps it into the entity.

Common scenarios:

- Normalizing legacy data in the document before mapping.
- Mapping compatible fields between an old schema and a new model.
- Supplying default values when reading documents missing a field.
- Normalizing an entity after the converter has converted types.
- Computing derived fields used only by the application.
- Attaching display metadata or runtime state to the entity.

Not every requirement should use a callback. If data must be fixed permanently in the index, perform a migration or data update. Read callbacks only modify objects passing through the current read flow; they do not automatically write changes back to the stored document.

## 3. AfterLoadCallback Works at the Document-Loaded Stage

`AfterLoadCallback` is invoked at the stage where Spring Data has received the document from Elasticsearch. This is the right moment to process data before or during conversion from document to entity, according to the contract of the version in use.

Example goal: old documents may lack a `status` field. The application wants to supply a default value on read:

~~~json
{
  "_id": "P-100",
  "_source": {
    "name": "Wireless Keyboard",
    "price": 79.5
  }
}
~~~

Meanwhile, the current model expects `status`. You can process the document at the load stage so the converter receives a compatible structure.

Pseudocode illustrating the idea:

~~~java
// Illustrative shape: use the exact parameters and return type
// of AfterLoadCallback in your installed Spring Data version.
Document onAfterLoad(Document document, IndexCoordinates index) {
    if (!document.containsKey("status")) {
        document.put("status", "UNKNOWN");
    }
    return document;
}
~~~

This operates on the intermediate document. The callback must return the object per the contract so the pipeline continues. Do not assume every API or release shares the exact same signature; check the interface in your actual dependency before implementing.

### Appropriate Uses for AfterLoadCallback

- Adjusting legacy field names or structure before mapping.
- Supplying default values per read conventions.
- Normalizing data representation at the document layer.
- Removing or transforming a technical field before the converter reads it, if required by mapping.

### Things Not to Do Here

- Calling external services per document.
- Running additional Elasticsearch queries inside the callback.
- Writing the document back during a read.
- Performing business operations with side effects.
- Implicitly altering the index schema.
- Putting critical authorization logic in the callback without clear enforcement at the service/API layer.

A callback can run on many documents within a single search request. Any slow operation or network call in the callback can increase latency for the entire page of results.

## 4. AfterConvertCallback Works After Entity Creation

`AfterConvertCallback` is invoked after Spring Data has converted the document into a Java object. The callback receives the entity and may also receive the original document and index information depending on the API contract.

Model example:

~~~java
public class Product {

    @Id
    private String id;

    private String name;

    private Double price;

    private String displayLabel;

    // getters and setters
}
~~~

The application wants to build `displayLabel` from the mapped fields. This fits an entity callback:

~~~java
@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        product.setDisplayLabel(
            product.getName() + " - " + product.getPrice()
        );

        return product;
    }
}
~~~

The signature above illustrates the common Spring Data Elasticsearch callback shape; verify the package, parameters, and return type in your release train.

The callback receives the entity already created by the converter. It can read typed Java domain fields rather than manually parsing maps from the document.

### AfterConvertCallback Can Modify the Entity

The callback can:

- Normalize strings after mapping.
- Populate derived runtime-only fields.
- Fill defaults on unset Java properties.
- Convert a legacy status into an enum or domain value.
- Attach computed metadata for responses.

If the callback mutates the entity and returns it, the object returned from the read flow carries those changes. That does not mean Elasticsearch saved the changes.

If changes must be persisted permanently, use the Update API, a migration, or a dedicated write flow. Do not expect `AfterConvertCallback` to persist automatically.

## 5. Distinguishing the Two Callbacks

| Criterion | AfterLoadCallback | AfterConvertCallback |
|---|---|---|
| Timing | After the document is loaded from Elasticsearch | After the converter turns the document into an entity |
| Processed Target | Document or load-stage representation per API contract | Mapped Java entity |
| Data Type | Field/document representation | Concrete domain type |
| Use Cases | Schema compatibility, raw data normalization | Entity normalization, derived fields |
| Writes back to index? | No | No |
| Depends on entity mapping? | Can run before mapping | Yes, because the entity is already created |
| Example | Populate missing default field on old documents | Build `displayLabel` from `name` and `price` |

Quick selection guide:

- Need to alter how the document is read or prepare it for the converter: consider `AfterLoadCallback`.
- Need to modify the Java object after mapping: consider `AfterConvertCallback`.
- Need to fix data stored in the index: use an update or migration.
- Need to tailor responses for a specific API: consider a mapper/DTO in the service rather than a global callback.

## 6. Registering Callbacks as Spring Beans

Entity callbacks are discovered by Spring through the application context's callback mechanism. The usual approach is declaring the callback as a bean using `@Component` or `@Bean`.

Component example:

~~~java
@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product entity,
            Document document,
            IndexCoordinates index) {

        if (entity.getName() != null) {
            entity.setDisplayLabel(entity.getName().trim());
        }

        return entity;
    }
}
~~~

Or configuration declaration:

~~~java
@Configuration
public class ElasticsearchCallbackConfiguration {

    @Bean
    ProductAfterConvertCallback productAfterConvertCallback() {
        return new ProductAfterConvertCallback();
    }
}
~~~

You do not need to invoke the callback manually from the repository. When registered properly in the Spring context and when Spring Data's read flow uses the entity callback infrastructure, the framework calls it at the corresponding lifecycle checkpoint.

### Callbacks Are Not Repository Fragments

A repository fragment is the right place to add a specialized query method or custom repository behavior. An entity callback is a hook in the mapping/persistence lifecycle. Do not use callbacks to replace repository methods or execute business queries.

## 7. Ordering When Multiple Callbacks Exist

An application can have multiple callbacks for the same entity type—for example, one callback that normalizes strings and another that builds a display field.

When order affects the result, declare order explicitly using Spring's ordering mechanism, such as `@Order` or `Ordered`, if your version's callback infrastructure supports it.

~~~java
@Component
@Order(10)
public class NormalizeProductName
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        if (product.getName() != null) {
            product.setName(product.getName().trim());
        }

        return product;
    }
}
~~~

~~~java
@Component
@Order(20)
public class BuildProductLabel
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        product.setDisplayLabel(product.getName());
        return product;
    }
}
~~~

In this example, the label-building callback runs after the name-normalizing callback. Without explicit ordering, do not rely on accidental bean discovery order.

Each callback should have a small, deterministic responsibility. If multiple callbacks modify the same property, tracking the final result becomes difficult.

## 8. Callback Scope and Read APIs to Watch Out For

Callbacks are invoked by Spring Data flows integrated with the entity callback infrastructure. APIs such as repository find/search or `ElasticsearchOperations` usually pass through the mapping converter when returning entities, though exact coverage depends on the operation type and version.

Distinguish between:

- Reading entities via repositories or Operations.
- Reading raw responses/documents.
- Using the converter directly.
- Using the Elasticsearch Java API Client directly.
- Using projections or custom DTOs.
- Reading aggregations without materializing entities.

If calling the Elasticsearch Java API Client directly and extracting `_source` yourself, do not assume Spring Data callbacks will run. Direct clients do not pass through the repository/template mapping lifecycle.

If a read flow returns raw `Document` or raw responses instead of entities, an entity `AfterConvertCallback` may not apply. Likewise, aggregation-only requests usually do not create domain entities per bucket, so do not expect entity callbacks to run on aggregation results.

Verify with integration tests for the exact API your application uses rather than generalizing from one read method to all APIs.

## 9. Callbacks with SearchHit and SearchHits

In searches, Spring Data can return `SearchHits<T>` or `SearchHit<T>` to preserve metadata such as ID, score, sort values, highlights, and inner hits.

Callbacks affect the entity content during the mapping lifecycle. Search hit metadata is a separate part of the search result.

Example:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits.getSearchHits()) {
    Product product = hit.getContent();

    // product may have passed through the corresponding callbacks.
    // hit still retains Elasticsearch result metadata.
    float score = hit.getScore();
}
~~~

Do not use callbacks to clear or overwrite `SearchHit` metadata. If you need to add distance, highlight snippets, or an extra label to a response, convert `SearchHit` to a DTO in the service layer.

A callback on an entity type affects every place reading that entity type through supported flows. DTO mapping in the service keeps presentation logic scoped to a specific API.

## 10. Combining Callbacks with Auditing

Auditing typically records when and by whom data was created or updated, such as:

- `createdDate`.
- `lastModifiedDate`.
- `createdBy`.
- `lastModifiedBy`.

This metadata belongs to the write lifecycle. Spring Data auditing normally uses annotations and an auditor provider to populate values when creating or updating an entity.

Example:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
~~~

Configuring auditing for Elasticsearch requires enabling the infrastructure for your version and providing an auditor if `createdBy`/`lastModifiedBy` are needed.

`AfterLoadCallback` and `AfterConvertCallback` run in the read flow. Do not use them to simulate `@LastModifiedDate` or alter audit timestamps merely when a user reads data. Doing so causes metadata to mutate on reads and misrepresents data history.

### When Can Read Callbacks Support Auditing?

Read callbacks can normalize or interpret legacy audit fields for compatibility with a new model, but they should not write read timestamps into modified fields. If tracking when a document was accessed is required, that is a distinct business event and should be recorded through an intentional write flow.

## 11. Callbacks and Application Events

Spring Data Elasticsearch has application events for lifecycle points such as load, convert, save, or delete depending on version. Entity callbacks and application events serve related but not identical purposes.

Entity callbacks generally fit when you need to modify an entity/document and return the adjusted object back into the pipeline. Application events fit when notifying listeners of a lifecycle event.

Do not use an event listener to modify an entity after the framework has already returned the result to the caller and expect those changes to appear in the returned object. If you need to transform values flowing through the pipeline, use a callback at the right checkpoint or a mapper/DTO in the service.

Also do not assume events and callbacks have equivalent ordering without verifying the contract of your Spring Data Elasticsearch version.

## 12. Callbacks in Reactive Applications

Spring Data Elasticsearch offers reactive APIs for non-blocking read flows. If the application uses reactive templates/repositories, check the reactive callback infrastructure supported by that version and its corresponding return contract.

Guidelines:

- Do not call blocking repositories or synchronous HTTP clients inside a reactive flow's callback.
- Do not call `block()` to fetch data from another service inside a callback.
- Keep callbacks lightweight, deterministic, and independent of the network.
- If asynchronous enrichment is needed, perform it in the reactive service pipeline after receiving the entity.
- Test both subscription and cancellation if the callback impacts reactive streams.

A synchronous callback registered for an imperative flow does not automatically mean it fits a reactive flow. Use the exact callback type provided by the reactive API in your release train.

## 13. Handling Nulls, Missing Fields, and Legacy Data

Documents in an index may have been created by multiple application versions. Therefore, read callbacks must tolerate missing fields, `null` values, and legacy data.

`AfterConvertCallback` example:

~~~java
@Override
public Product onAfterConvert(
        Product product,
        Document document,
        IndexCoordinates index) {

    if (product.getName() == null) {
        product.setName("Unnamed product");
    }

    if (product.getDisplayLabel() == null) {
        product.setDisplayLabel(product.getName());
    }

    return product;
}
~~~

Do not silently replace corrupted data with default values if doing so masks real data issues. For business-required fields, record metrics or detect errors in the service.

If a callback alters fields before the converter, ensure the data type matches the mapping/converter. For example, a numeric field should not be assigned an arbitrary string.

### Backward Compatibility Does Not Replace Migration

Callbacks can serve as a temporary bridge when reading old documents. If the entire index must transition to a new schema, migrating or reindexing makes data consistent and eliminates compatibility logic running on every single read forever.

Set a deadline or condition for removing legacy callbacks once migration completes.

## 14. Performance and Side Effects

Callbacks can run many times in a single search request because each hit may go through mapping. A search returning 100 hits can invoke the callback for many entities.

Therefore:

- Do not make HTTP or database calls per hit.
- Do not run nested Elasticsearch queries.
- Do not log the entire entity on every read.
- Avoid heavy CPU computation on large fields.
- Avoid allocating unnecessarily large objects or collections.
- Do not store entities in static caches or mutable singletons.
- Do not mutate state shared across requests.

If enrichment from another service is needed, consider batch lookup at the service layer: collect IDs from the page, fetch supplementary data once, and assemble it into DTOs.

Callbacks should be deterministic: the same input document and configuration should produce the same output. This guarantees re-reading a document does not trigger different side effects.

## 15. How Are Exceptions in Callbacks Handled?

If a callback throws an exception, the read flow can fail depending on where the callback was called and how the framework wraps exceptions. A buggy callback can prevent the entire read operation from returning results, even though Elasticsearch already returned the documents successfully.

Do not swallow all exceptions:

~~~java
try {
    // callback logic
} catch (Exception ex) {
    // Do not silently ignore all errors.
}
~~~

Instead:

- Determine which errors are recoverable with defaults.
- Determine which errors must fail the request.
- Log with context such as index and document ID where permitted.
- Do not log full payloads if they contain sensitive data.
- Use metrics to detect rates of legacy documents or mapping failures.
- Keep exceptions clear so services can classify them.

If a callback processes untrusted data, validate it before placing values into entities or responses.

## 16. Complete Example: Normalizing Product After Reading

Suppose the application needs to trim the name and build a display label after the converter has mapped the entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    private Double price;

    @Transient
    private String displayLabel;

    // getters and setters
}
~~~

Callback:

~~~java
@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product product,
            Document document,
            IndexCoordinates index) {

        if (product.getName() != null) {
            product.setName(product.getName().trim());
        }

        if (product.getName() != null && product.getPrice() != null) {
            product.setDisplayLabel(
                product.getName() + " - " + product.getPrice()
            );
        }

        return product;
    }
}
~~~

The `displayLabel` property is marked transient if you do not want Spring Data to store it as a document field. The specific annotation may be `@Transient` from the Spring Data mapping package; check the proper import in your project.

When reading via Operations:

~~~java
Product product = operations.get(
    "P-100",
    Product.class,
    IndexCoordinates.of("products")
);
~~~

If the `get` flow of your version routes through the entity callback infrastructure, the returned entity will have `displayLabel` populated. Reading with a direct client and manually parsing JSON will not automatically run this callback.

### Do Not Turn Callbacks into Formatting for Every API

If `displayLabel` is only used by one endpoint, a DTO mapper in the service may be more appropriate. Callbacks on an entity type have broad scope and can cause other callers to receive transformed entities they did not expect.

## 17. Example: Normalizing a Legacy Document Before Conversion

Suppose an older index stored `product_name`, while the new entity uses `name`. A load-stage callback can prepare the document so the converter reads the new field, if the callback contract and mapping converter permit that operation.

Pseudocode:

~~~java
Document onAfterLoad(Document document, IndexCoordinates index) {
    if (!document.containsKey("name")
            && document.containsKey("product_name")) {
        document.put("name", document.get("product_name"));
    }

    return document;
}
~~~

Check the actual field name the converter expects, including `@Field(name = "...")` and naming strategies. If the index mapping still uses the old field, the proper fix may be updating mapping/entity metadata or migrating rather than aliasing fields inside a callback.

Do not delete the old field from the intermediate document if the converter or other logic still needs it. The callback only modifies the representation currently being read; it does not alter `_source` in the index.

## 18. Testing AfterLoadCallback and AfterConvertCallback

Callbacks should be tested at two levels:

**Callback unit tests:** pass sample documents/entities and assert the callback returns the expected output. These tests are fast and useful for null branches, missing fields, and legacy values.

**Integration tests:** read documents from a compatible Elasticsearch instance using the application's actual repository or Operations API, verifying the framework invokes the callback at the right time and produces the right final result.

Example testing `AfterConvertCallback`:

~~~java
@Test
void createsDisplayLabelAfterConversion() {
    Product product = new Product();
    product.setName(" Wireless Keyboard ");
    product.setPrice(79.5);

    Product result = callback.onAfterConvert(
        product,
        Document.create(),
        IndexCoordinates.of("products")
    );

    assertThat(result.getName()).isEqualTo("Wireless Keyboard");
    assertThat(result.getDisplayLabel())
        .isEqualTo("Wireless Keyboard - 79.5");
}
~~~

Constructor and callback signatures in tests must match the API version in use.

### Integration Test Scenarios

- Reading a document with all fields present.
- Reading a document missing legacy fields.
- Reading a document with null values.
- Reading via repository `findById`.
- Reading via `ElasticsearchOperations.get` or `search`.
- Search returning multiple hits and callback running on entity content.
- Callbacks invoked in configured order when multiple callbacks exist.
- Raw client reading a document does not trigger Spring Data callbacks.
- Callback throwing an exception and the service handling it per policy.
- `@Transient` fields are not written back when saving the entity.

Do not merely call the callback method directly and conclude the framework registered it properly. At least one integration test must traverse the real read flow.

## 19. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Callback does not run | Callback is not a Spring bean or read API bypasses Spring Data mapping | Check component scan and read flow |
| Callback runs with Operations but not with direct client | Direct client bypasses Spring Data callback infrastructure | Call mapper manually or use Operations |
| Entity changes but index does not | Read callbacks only modify the returned object | Use Update API or migration if persistence is needed |
| Legacy field is not mapped | Handled at wrong checkpoint or field name does not match converter | Check mapping and AfterLoad contract |
| `displayLabel` gets saved to the index | Field is not marked transient or mapping allows saving it | Mark field runtime-only |
| Search slows down after adding callback | Callback makes network calls or heavy computations per hit | Move enrichment to batch service |
| Multiple callbacks produce unstable results | Ordering not declared or both modify the same field | Use `@Order` and separate responsibilities |
| Audit timestamp changes on read | Using read callback to modify auditing fields | Only update audit fields in the write lifecycle |
| Failing callback breaks entire search | Exception not handled per policy | Classify errors and log with context |
| Reactive request hangs | Callback performs blocking I/O | Use reactive contract or enrichment in reactive pipeline |

## 20. Choosing a Callback vs. Handling in the Service

| Need | Appropriate Place |
|---|---|
| Normalize document before converter maps | `AfterLoadCallback` |
| Adjust entity after mapping | `AfterConvertCallback` |
| Create response field for just one endpoint | DTO mapper/service |
| Enrichment requiring calls to multiple services | Service layer, preferring batching |
| Record created/modified metadata | Auditing in the write lifecycle |
| Fix data persistently in the index | Update API or migration |
| Add business queries | Repository or `ElasticsearchOperations` |
| Handle raw responses from direct client | Application-managed adapter/converter |

Callbacks should hold shared, lightweight logic tightly coupled to the read lifecycle. Business logic with many dependencies or scoped to a single use case belongs in the service.

## 21. Read Callback Implementation Checklist

- [ ] Clearly determine whether to process the document before mapping or the entity after mapping.
- [ ] Use `AfterLoadCallback` for the load stage per your version's contract.
- [ ] Use `AfterConvertCallback` for entities already created by the converter.
- [ ] Register callbacks as Spring beans.
- [ ] Verify the callback is invoked by the repository/Operations APIs in use.
- [ ] Do not assume direct `ElasticsearchClient` automatically invokes Spring Data callbacks.
- [ ] Keep callbacks lightweight, deterministic, and free of unintended side effects.
- [ ] Handle nulls, missing fields, and legacy data.
- [ ] Declare ordering if multiple callbacks depend on one another.
- [ ] Mark runtime-only fields appropriately so they are not written back to the index.
- [ ] Do not use read callbacks to update auditing timestamps.
- [ ] Use Update API or migration if changes must be stored durably.
- [ ] Do not call blocking I/O inside reactive flows.
- [ ] Write unit tests for callback logic.
- [ ] Write integration tests exercising the real read flow.

`AfterLoadCallback` and `AfterConvertCallback` let you intervene at two distinct points in the Elasticsearch read process. `AfterLoadCallback` processes the document at the load stage according to your version's contract; `AfterConvertCallback` processes the entity after the converter has mapped it. Both affect only the data passing through the read flow and do not automatically write changes back to the index. Keeping callbacks lightweight, properly registered in the Spring context, and placed in the right layer ensures consistent data reads without turning callbacks into containers for business logic or side effects.
