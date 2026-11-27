# Controlling the Target Index with IndexCoordinates When Using Operations

Spring Data Elasticsearch normally resolves the default index name from an entity's @Document annotation. This is convenient when all documents of a type live in the same index. However, for data partitioned by month, tenant, environment, or another business rule, a single entity may need to be written to and read from multiple indices.

ElasticsearchOperations supports passing IndexCoordinates into individual operations. This allows a service to decide the target index at the time a CRUD operation executes, rather than relying solely on the default index name in entity metadata.

IndexCoordinates is an object describing the index or alias that an operation will target. It does not create the index automatically, does not alter the entity's mapping, and does not store that choice on the Java object. To read the right document back, the application must use the corresponding index or alias.

## 1. Default Index from Entity Metadata

An entity typically declares its index with @Document:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String customerId;

    @Field(type = FieldType.Long)
    private Long totalInCents;

    // constructors, getters and setters
}
~~~

When calling operations without passing IndexCoordinates:

~~~java
operations.save(order);

Order saved = operations.get(
    order.getId(),
    Order.class
);

boolean exists = operations.exists(
    order.getId(),
    Order.class
);
~~~

Spring Data uses the index metadata of Order, which in this example is orders. This fits when an entity always operates on a fixed logical index.

If you need to write an order to orders-2026-11, you can pass the target index directly:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

operations.save(order, target);
~~~

Here, the save operation uses the index specified in target. The default index name on @Document remains part of the entity's metadata and is still used by other operations that do not pass coordinates.

The two call styles have different meanings:

| Call | Resolved index |
|---|---|
| operations.save(order) | Default index in @Document |
| operations.save(order, coordinates) | Index/alias in IndexCoordinates |
| operations.get(id, Order.class) | Default index in @Document |
| operations.get(id, Order.class, coordinates) | Explicitly passed index/alias |

Be consistent in how you choose indices across write, read, existence check, count, and delete operations. Writing to one index while reading from the default index is a common reason applications think documents disappeared.

## 2. What Is IndexCoordinates?

IndexCoordinates belongs to the package:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
~~~

Creating coordinates for a single index:

~~~java
IndexCoordinates index =
    IndexCoordinates.of("orders-2026-11");
~~~

You can use an alias name:

~~~java
IndexCoordinates index =
    IndexCoordinates.of("orders-write");
~~~

And for multi-index read operations, you can specify multiple index names:

~~~java
IndexCoordinates indexes = IndexCoordinates.of(
    "orders-2026-10",
    "orders-2026-11",
    "orders-2026-12"
);
~~~

IndexCoordinates only carries the target information. Elasticsearch is responsible for resolving the index name or alias and executing the request.

Distinguish three concepts:

- **Entity metadata**: describes the domain type, ID, field mappings, and default index.
- **IndexCoordinates**: specifies the index/alias for a single Operations call.
- **IndexOperations**: index-management API for existence checks, index creation, mappings, settings, refreshes, and index deletion.

IndexCoordinates is not an index-creation command. Passing a non-existent index name to save does not replace proper provisioning and mapping setup.

## 3. Writing Documents to a Selected Index

Example service selecting the index by business month:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class MonthlyOrderService {

    private static final DateTimeFormatter MONTH_FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    private final ElasticsearchOperations operations;

    public MonthlyOrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    private IndexCoordinates indexFor(LocalDate businessDate) {
        String indexName =
            "orders-" + businessDate.format(MONTH_FORMAT);

        return IndexCoordinates.of(indexName);
    }

    public Order save(Order order, LocalDate businessDate) {
        return operations.save(order, indexFor(businessDate));
    }
}
~~~

Example:

- An order with business date 2026-11-13 is written to orders-2026-11.
- An order with business date 2026-12-02 is written to orders-2026-12.

The Order entity is still used to convert the Java object into a document. IndexCoordinates determines where the document is written for that call.

Choose the business date consistently. If data arrives across multiple time zones, normalize the time zone before converting a timestamp into a month. Do not rely on the server's default system date if business rules specify a different time zone.

### 3.1. Writing Multiple Documents to the Same Index

Operations also offers collection-write overloads accepting IndexCoordinates. Illustrative example:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

List<Order> orders = loadOrdersForNovember();

operations.save(orders, target);
~~~

All documents in the collection are sent to the selected index. If documents belong to different months, group them by month and write each group to its corresponding index, or execute operations with coordinates computed per record.

Do not lump documents from different partitions into one write call with a single shared target index if storage rules require them to live in separate indices.

## 4. Reading a Document by ID from the Right Index

After writing to a dynamic index, the get operation must receive the matching coordinates:

~~~java
public Order findById(String id, LocalDate businessDate) {
    IndexCoordinates target = indexFor(businessDate);

    return operations.get(
        id,
        Order.class,
        target
    );
}
~~~

An Elasticsearch ID only needs to be unique within an index. Two different indices can both hold a document whose _id is O-1001.

Example:

~~~text
orders-2026-10
    _id = O-1001
    customerId = C-10

orders-2026-11
    _id = O-1001
    customerId = C-25
~~~

If you only know the ID without knowing the index, the application does not have enough information to uniquely identify the document. Store the partition key alongside the ID, look up an appropriate registry, or read through an alias covering the necessary indices.

Do not assume IDs are automatically unique across all indices.

### 4.1. Creating a Shared Index Resolver

To avoid scattering index-naming logic everywhere, centralize the index selection rule in a dedicated component:

~~~java
@Component
public class OrderIndexResolver {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    public IndexCoordinates forDate(LocalDate businessDate) {
        String name = "orders-" + businessDate.format(FORMAT);
        return IndexCoordinates.of(name);
    }
}
~~~

The service uses the same resolver for save, get, exists, and delete:

~~~java
@Service
public class OrderService {

    private final ElasticsearchOperations operations;
    private final OrderIndexResolver indexResolver;

    public OrderService(
            ElasticsearchOperations operations,
            OrderIndexResolver indexResolver) {
        this.operations = operations;
        this.indexResolver = indexResolver;
    }

    public Order save(Order order, LocalDate date) {
        return operations.save(order, indexResolver.forDate(date));
    }

    public Order find(String id, LocalDate date) {
        return operations.get(
            id,
            Order.class,
            indexResolver.forDate(date)
        );
    }

    public boolean exists(String id, LocalDate date) {
        return operations.exists(
            id,
            Order.class,
            indexResolver.forDate(date)
        );
    }

    public String delete(String id, LocalDate date) {
        return operations.delete(
            id,
            Order.class,
            indexResolver.forDate(date)
        );
    }
}
~~~

Method names and overloads may vary across Spring Data Elasticsearch generations. Verify signatures against your project's actual dependency. The design principle is using a unified resolver so every operation targets the same partition.

## 5. Checking Existence and Deleting with IndexCoordinates

When documents reside in dynamic indices, exists and delete must also specify the target index.

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

boolean found = operations.exists(
    "O-1001",
    Order.class,
    target
);

if (found) {
    operations.delete(
        "O-1001",
        Order.class,
        target
    );
}
~~~

If coordinates are omitted, Spring Data can check or delete the document in the entity's default index rather than the November index.

This is why the same index-resolution rule must flow through the entire CRUD path:

| Operation | Operations API with coordinates |
|---|---|
| Save one object | save(entity, indexCoordinates) |
| Save a collection | save(entities, indexCoordinates) |
| Read by ID | get(id, entityClass, indexCoordinates) |
| Check existence by ID | exists(id, entityClass, indexCoordinates) |
| Delete by ID | delete(id, entityClass, indexCoordinates) |
| Search | search(query, entityClass, indexCoordinates) |
| Count | count(query, entityClass, indexCoordinates) |

Check the overloads available in your Spring Data Elasticsearch version. Some APIs may change parameter names or return types between versions.

### 5.1. Deleting a Document vs. Deleting an Index

Distinguish clearly:

~~~java
// Delete one document by ID:
operations.delete(id, Order.class, target);

// Manage/delete the entire index:
operations.indexOps(target).delete();
~~~

The first command deletes the document identified by the ID and index. The second deletes the entire specified index. Never call IndexOperations.delete() when you only want to delete a single document.

## 6. Searching on a Specified Index

You can search within a dynamic index:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

Query query = new CriteriaQuery(
    new Criteria("customerId").is("C-100")
);

SearchHits<Order> hits = operations.search(
    query,
    Order.class,
    target
);
~~~

Here:

- Query describes the search condition.
- Order.class specifies the Java type used to map the results.
- IndexCoordinates specifies the target index/alias to search.

When you need to search data across multiple months, you can pass multiple indices:

~~~java
IndexCoordinates history = IndexCoordinates.of(
    "orders-2026-09",
    "orders-2026-10",
    "orders-2026-11"
);

SearchHits<Order> hits = operations.search(
    query,
    Order.class,
    history
);
~~~

This works well when mappings across the indices are compatible. If a field has the same name but different types across indices, queries, sorting, or aggregations can fail or behave unexpectedly.

Bound the number of indices queried. Wildcards or overly broad lists can force Elasticsearch to fan out across many shards and increase latency.

### 6.1. Counting on a Dynamic Index

To count documents matching a condition in an index:

~~~java
long total = operations.count(
    query,
    Order.class,
    IndexCoordinates.of("orders-2026-11")
);
~~~

To count all documents in the index, use the match-all query provided by your Spring Data version's API:

~~~java
long total = operations.count(
    Query.findAll(),
    Order.class,
    IndexCoordinates.of("orders-2026-11")
);
~~~

When counting across multiple indices, pass coordinates containing the exact indices to include. The result is the document count across the resolved indices.

Count and Search depend on refresh visibility. Newly written documents may not appear in queries until the next refresh. If business logic requires immediate results after writing, configure an appropriate refresh policy.

## 7. Using Aliases as the Target Index

An application can operate through an alias instead of a physical index name:

~~~java
IndexCoordinates writeTarget =
    IndexCoordinates.of("orders-write");

operations.save(order, writeTarget);
~~~

Aliases let the application keep a stable logical name while underlying physical indices rotate through rollover or migrations.

Example:

~~~text
orders-write  ---> orders-2026-11
orders-read   ---> orders-2026-09
              ---> orders-2026-10
              ---> orders-2026-11
~~~

The application writes through orders-write and reads history through orders-read.

A read alias can point to multiple indices. A write alias must have a clear write index if it points to multiple indices. If the alias lacks a valid write index, write requests may be rejected by Elasticsearch.

Inspect aliases via the REST API:

~~~http
GET /_cat/aliases?v
~~~

View alias metadata:

~~~http
GET /_alias/orders-write
~~~

IndexCoordinates simply carries the alias name. Elasticsearch resolves which index the alias points to and which index receives writes.

## 8. Managing Indices and Mappings Before Writing

IndexCoordinates does not automatically create indices or ensure valid mappings. With dynamic indices, the application or provisioning pipeline must create the index before use.

You can check and manage indices with IndexOperations:

~~~java
IndexCoordinates target =
    IndexCoordinates.of("orders-2026-11");

IndexOperations indexOperations =
    operations.indexOps(target);

if (!indexOperations.exists()) {
    indexOperations.create();

    Document mapping =
        operations.indexOps(Order.class).createMapping();

    indexOperations.putMapping(mapping);
}
~~~

This example creates the index and applies the mapping derived from the Order entity. If the entity declares analyzers, normalizers, custom settings, or complex mappings, provision the full settings and mappings before writing.

In supported versions, you can use index-creation APIs with mappings such as createWithMapping() on IndexOperations. Check the API of your version and ensure entity settings are applied when needed.

### 8.1. Do Not Let Every Request Create Indices Concurrently

The check-then-create pattern:

~~~java
if (!indexOperations.exists()) {
    indexOperations.create();
}
~~~

can hit a race condition when multiple initial requests run concurrently. One request succeeds in creating the index while the others receive an error because the index already exists.

In production systems, manage index creation via migrations, synchronized startup provisioning, or a dedicated admin component. If still created at runtime, handle already-exists errors specifically without ignoring permission, mapping, or connection errors.

Do not create a new index on every save without an index-count and lifecycle management strategy.

### 8.2. Mappings Must Be Compatible Across Indices

The same entity can be written to multiple indices, but each index must have mappings compatible with the entity's data and queries.

For example, if Order.totalInCents is a Long:

~~~json
{
  "properties": {
    "totalInCents": {
      "type": "long"
    }
  }
}
~~~

If an older index declared that field as keyword, writing or querying via the entity can fail or yield inconsistent semantics.

When changing mappings, create a new index and migrate data according to a plan rather than assuming editing Java annotations updates existing indices.

## 9. IndexCoordinates and Repositories

Standard repositories use the entity's index metadata:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
~~~

Calls such as:

~~~java
orderRepository.save(order);
orderRepository.findById(id);
orderRepository.deleteById(id);
~~~

do not accept per-operation IndexCoordinates. They target the index determined from metadata and repository configuration.

When per-request index selection is needed, ElasticsearchOperations is the more suitable abstraction:

~~~java
operations.save(order, target);
operations.get(id, Order.class, target);
~~~

Both repositories and Operations can coexist in the same application:

- Repositories handle CRUD against a fixed logical index.
- Operations handles flows requiring dynamic index selection or custom queries.
- Both can share mapping metadata and client configuration when configured accordingly.

Do not expect a repository call after saving with IndexCoordinates to automatically know which dynamic index holds the document. When mixing both abstractions, make sure each operation's target index is explicit.

## 10. Selecting an Index by Tenant

A common case is partitioning data by tenant:

~~~java
public Order saveForTenant(String tenantId, Order order) {
    String validatedTenant = validateTenantId(tenantId);

    IndexCoordinates target = IndexCoordinates.of(
        "orders-" + validatedTenant
    );

    return operations.save(order, target);
}
~~~

The tenant identifier must be validated and obtained from an authenticated security context. Never concatenate raw strings sent by an HTTP client directly into an index name.

Example simple validator:

~~~java
private String validateTenantId(String tenantId) {
    if (tenantId == null ||
            !tenantId.matches("[a-z0-9-]{1,40}")) {
        throw new IllegalArgumentException("Invalid tenant id");
    }

    return tenantId;
}
~~~

The validator checks only format. The service must still verify that the current user is authorized to access that tenant.

Dedicated per-tenant indices do not automatically establish a complete security boundary. Elasticsearch accounts, application-layer authorization, tenant verification, and access rules must be designed together.

If there are tens of thousands of tenants, creating a separate index per tenant can balloon shard counts and operational overhead. Consider a shared index with a tenant field and mandatory filters, or partitioning by tenant tier/group when appropriate for load and isolation needs.

## 11. Index Names and Input Data

Dynamic index names are commonly assembled from a fixed prefix and a data segment such as tenant or month:

~~~java
String indexName = "orders-" + yearMonth;
IndexCoordinates target = IndexCoordinates.of(indexName);
~~~

Rules to follow:

- Use lowercase characters.
- Bound character set and length.
- Do not include spaces or characters forbidden by Elasticsearch in index names.
- Do not allow names starting with forbidden prefixes such as -, _, or +.
- Do not let clients pass arbitrary wildcards unless business rules explicitly require it.
- Do not let users pick indices outside their authorized scope.
- Use the exact same naming convention for writes, reads, backups, and retention.

Never treat index-name validation as authorization. A syntactically valid name can still point to data a user is forbidden to access.

## 12. Handling IDs and Routing

IndexCoordinates chooses the index or alias. It does not replace a document's routing key.

Elasticsearch can use custom routing to select shards. If a document was written with a routing value, get, exists, or delete operations must pass that same routing value to locate the document accurately.

REST API example:

~~~http
GET /orders-2026-11/_doc/O-1001?routing=tenant-a
~~~

If the application uses per-tenant routing, manage both the target index and the routing value together in the same business context. Do not assume IndexCoordinates carries routing.

Additionally, the same ID can appear in multiple indices. A get call with the right ID against the wrong index can still return not found or a completely different document sharing that ID.

Retain enough context to identify a document unambiguously, such as ID, partition date/tenant, and routing key if your system uses them.

## 13. Common Pitfalls

| Symptom | Possible cause | Troubleshooting step |
|---|---|---|
| Save succeeds but get returns null | Reading from default index instead of dynamic index | Pass the same IndexCoordinates for both writes and reads |
| exists returns false even though document was written | Wrong index, alias, or routing | Check actual index, alias, and routing |
| Delete misses the intended document | Delete hit the default index or an identical ID in another index | Pass the right coordinates and verify ID |
| Index does not exist | Target index not provisioned yet | Check exists and index/mapping provisioning flow |
| Mapper error on write | Target index mapping incompatible with entity | Inspect the actual index mapping |
| Search does not see the new document | Index not refreshed yet | Refresh in tests or review refresh policy |
| Multi-index search throws error | Incompatible mappings across indices | Compare mappings and standardize schema |
| Writing via alias rejected | Multi-index alias has no write index | Check alias and is_write_index |
| Tenant can access another tenant's index | Unchecked user input instead of authorization | Derive tenant from principal and enforce permissions |
| Repository cannot find document saved via Operations | Repository still queries @Document's index | Use Operations with coordinates or unify index/alias design |

## 14. Debugging Process When Data Is Not in the Expected Index

When save or get behaves unexpectedly, verify the actual index used by each operation.

**Step 1 — Identify the entity's default index**

Check @Document(indexName = ...) and related mapping configuration.

**Step 2 — Identify the coordinates passed**

Log the index/alias name returned by the resolver. Avoid logging sensitive payloads or credentials.

**Step 3 — Inspect indices and aliases in Elasticsearch**

~~~http
GET /_cat/indices?v
GET /_cat/aliases?v
~~~

Confirm the index exists and the alias resolves properly.

**Step 4 — Read the document directly by index**

~~~http
GET /orders-2026-11/_doc/O-1001
~~~

If the document exists in a different index, the application's index-selection logic is inconsistent.

**Step 5 — Inspect mappings**

~~~http
GET /orders-2026-11/_mapping?pretty
~~~

Compare field types with entity metadata.

**Step 6 — Verify the entire CRUD path**

Ensure save, get, exists, search, count, and delete all use the same index-selection rule. If an operation intentionally uses an alias or multiple indices, document that difference clearly in the service.

## 15. Complete Example: Monthly Order Management Service

The example below encapsulates index selection inside a resolver and uses it across CRUD operations:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Component
class OrderIndexResolver {

    private static final DateTimeFormatter FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    IndexCoordinates forDate(LocalDate date) {
        return IndexCoordinates.of(
            "orders-" + date.format(FORMAT)
        );
    }
}

@Service
public class OrderStore {

    private final ElasticsearchOperations operations;
    private final OrderIndexResolver indexResolver;

    public OrderStore(
            ElasticsearchOperations operations,
            OrderIndexResolver indexResolver) {
        this.operations = operations;
        this.indexResolver = indexResolver;
    }

    public Order save(Order order, LocalDate businessDate) {
        return operations.save(
            order,
            indexResolver.forDate(businessDate)
        );
    }

    public Order find(String id, LocalDate businessDate) {
        return operations.get(
            id,
            Order.class,
            indexResolver.forDate(businessDate)
        );
    }

    public boolean exists(String id, LocalDate businessDate) {
        return operations.exists(
            id,
            Order.class,
            indexResolver.forDate(businessDate)
        );
    }

    public String delete(String id, LocalDate businessDate) {
        return operations.delete(
            id,
            Order.class,
            indexResolver.forDate(businessDate)
        );
    }
}
~~~

This example assumes monthly indices have already been created with compatible mappings before the service writes data. It also assumes businessDate has already been normalized to the system's time zone.

When historical search across multiple months is required, the service can construct coordinates containing the authorized indices and invoke search with the same domain type. Avoid overly broad index patterns when only a few months of data are needed.

## 16. Quick Reference Table

| Need | Usage |
|---|---|
| Use default index from entity | operations.save(entity) |
| Write to a specific index | operations.save(entity, coordinates) |
| Read by ID in a specific index | operations.get(id, Entity.class, coordinates) |
| Check existence in a specific index | operations.exists(id, Entity.class, coordinates) |
| Delete document by ID | operations.delete(id, Entity.class, coordinates) |
| Search on a specific index | operations.search(query, Entity.class, coordinates) |
| Count on a specific index | operations.count(query, Entity.class, coordinates) |
| Manage target index | operations.indexOps(coordinates) |
| Read multiple indices | IndexCoordinates.of(indexA, indexB, ...) |
| Write via alias | IndexCoordinates.of("write-alias") with configured write index |

IndexCoordinates lets ElasticsearchOperations select an explicit index or alias per call. Use a unified index-selection rule across save, get, exists, and delete; use aliases to decouple logical names from physical indices; manage mappings/lifecycles before writing; and enforce tenant, routing, and access control in the application layer. When data must be routed dynamically per operation, passing explicit coordinates ensures the service knows exactly where each document is read or written.
