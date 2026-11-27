# Dynamic Index Names via Expressions and IndexCoordinates

In Spring Data Elasticsearch, an entity is typically mapped to an index via the `@Document` annotation. The simplest declaration uses a fixed name:

```java
@Document(indexName = "orders")
public class Order {
    // fields
}
```

This suits cases where every document of the entity is stored in the same index. However, some applications need to choose an index by deployment environment, tenant, data creation date, or a partitioning rule. In such cases, you need to understand two distinct mechanisms:

- **Expressions in `@Document(indexName = ...)`** allow the index name to be resolved from configuration or Spring Expression Language (SpEL) when Spring Data builds the entity's metadata.
- **`IndexCoordinates`** allows passing an explicit target index into individual `ElasticsearchOperations` calls, enabling one entity to be written to, read from, or searched across different indexes depending on the request context.

These two mechanisms solve different needs. Annotation expressions suit stable index names determined by application configuration; `IndexCoordinates` suits target indexes that vary per operation. Do not use annotation expressions as a way to fetch the current tenant per request, because entity metadata is typically constructed and cached for the application lifecycle.

## 1. Index Name in Entity Metadata

Spring Data Elasticsearch uses mapping metadata to convert Java objects into Elasticsearch documents. The `@Document` annotation provides entity-level information, including the index name.

Example:

```java
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

    @Field(type = FieldType.Double)
    private Double total;

    // constructors, getters and setters
}
```

With the declaration above, Spring Data uses the `orders` index as the default index for the `Order` entity. Standard repository operations such as:

```java
orderRepository.save(order);
orderRepository.findById("O-1001");
orderRepository.findAll();
```

execute according to the entity's metadata. Repositories do not take a separate target index parameter on every call; the index name is determined from the entity's mapping configuration and the repository mechanism.

This is a good fit if:

- The application has one logical index for the entity.
- Each environment can configure a different index name at startup.
- Repositories are the primary abstraction and per-request index selection is unnecessary.
- Partitioning is managed via aliases or Elasticsearch's index mechanisms.

When one entity needs to be saved across multiple indexes by time or tenant, merely changing `@Document` values is insufficient to express dynamic per-call selection. Switch to operations that accept `IndexCoordinates`.

## 2. Using SpEL in the `indexName` Attribute

Spring Data Elasticsearch supports expressions in `@Document`'s `indexName`. Expressions are written in Spring Expression Language syntax, enclosed in `#{...}`.

For example, create a bean providing the index name from deployment configuration:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component("indexNameProvider")
public class IndexNameProvider {

    private final String ordersIndex;

    public IndexNameProvider(
            @Value("${app.elasticsearch.orders-index:orders}") String ordersIndex) {
        this.ordersIndex = ordersIndex;
    }

    public String ordersIndex() {
        return ordersIndex;
    }
}
```

Then reference the bean in the annotation:

```java
@Document(indexName = "#{@indexNameProvider.ordersIndex()}")
public class Order {
    // fields
}
```

In the example:

- `@Value("${app.elasticsearch.orders-index:orders}")` reads the `app.elasticsearch.orders-index` property; if absent, it defaults to `orders`.
- `@indexNameProvider` references the Spring bean named `indexNameProvider`.
- `ordersIndex()` returns the index name used in mapping metadata.

It can be configured per environment:

```yaml
# application.yml
app:
  elasticsearch:
    orders-index: orders
```

```yaml
# application-prod.yml
app:
  elasticsearch:
    orders-index: orders-prod
```

When running with the production profile, Spring loads the corresponding property and entity metadata uses the configured index name.

### 2.1. Distinguishing Placeholders and SpEL

The example above uses two different syntaxes:

| Syntax | Mechanism | Example |
|---|---|---|
| `${...}` | Spring property placeholder | `${app.elasticsearch.orders-index:orders}` |
| `#{...}` | Spring Expression Language | `#{@indexNameProvider.ordersIndex()}` |

Placeholders pull values from configurations such as `application.yml`, environment variables, or property sources. SpEL can evaluate an expression, invoke a method on a bean, or reference values in the Spring context.

You can combine both mechanisms: a bean receives a property via `@Value`, and the annotation invokes the bean via SpEL. This keeps index name configuration in one place while keeping entity metadata readable.

### 2.2. When Expressions Are Evaluated

An important point is that expressions in `@Document` belong to entity metadata. Spring Data typically builds and caches metadata for the lifetime of the application context. Therefore, treat the index name from an annotation expression as a stable configuration value for the running application.

Do not write a bean method that reads the current tenant from a request context and use that method in `@Document`, expecting each request to receive a different index. Metadata may have already been evaluated earlier and shared across requests. The result may be every request hitting the same index, or behavior depending on when metadata was initialized.

If the index must vary by tenant, date, or an attribute of each operation, compute the index name in a service and pass it via `IndexCoordinates`.

### 2.3. When Should Annotation Expressions Be Used?

Annotation expressions suit stable values such as:

- Different index names across local, test, staging, and production environments.
- Index names with a suffix based on a deployment configuration.
- Index names provided by a configuration bean at application startup.

Do not use them as a dynamic per-request routing mechanism by tenant or user. Also do not feed raw request input directly into SpEL expressions; index names must be determined and controlled by the application.

## 3. What Is `IndexCoordinates`?

`IndexCoordinates` is a Spring Data Elasticsearch type representing one or more index names targeted by an operation. Instead of implicitly deriving the target index from `@Document`, code can explicitly pass the index to use.

Import:

```java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
```

Create an instance:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-2026-11");
```

The value `orders-2026-11` is the index name the operation will use. `IndexCoordinates` does not create indexes, save documents, or execute queries itself; it merely describes the target index for APIs that accept this parameter.

Overloads in `ElasticsearchOperations` allow passing explicit coordinates. Example:

```java
operations.save(order, coordinates);

operations.get("O-1001", Order.class, coordinates);

operations.search(query, Order.class, coordinates);

operations.delete("O-1001", Order.class, coordinates);
```

Method names or overloads may differ depending on the Spring Data Elasticsearch generation your project uses. Check the API of your actual dependency if the project uses an older version. The general principle remains: specify the index with `IndexCoordinates` on operations requiring dynamic routing.

## 4. Using `IndexCoordinates` to Write to Dynamic Indexes

Suppose an application stores orders by month. A service can determine the index based on the business date:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Service;

@Service
public class OrderSearchService {

    private static final DateTimeFormatter INDEX_MONTH =
        DateTimeFormatter.ofPattern("yyyy-MM");

    private final ElasticsearchOperations operations;

    public OrderSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order save(Order order, LocalDate businessDate) {
        String indexName = "orders-" + businessDate.format(INDEX_MONTH);
        IndexCoordinates coordinates = IndexCoordinates.of(indexName);

        return operations.save(order, coordinates);
    }
}
```

Example:

- An order with business date `2026-11-13` is written to `orders-2026-11`.
- An order with business date `2026-12-02` is written to `orders-2026-12`.

The same `Order` class is still used to convert the document. `IndexCoordinates` determines which index the document is written to on that call.

In practice, use a clearly defined business date with a consistent timezone. Do not arbitrarily take the server's local date if data can arrive from multiple timezones or requires business cutoff rules.

### 4.1. Reading Back from the Right Index

When writing to monthly indexes, reading by ID must also specify the right index:

```java
public Order findById(String id, LocalDate businessDate) {
    String indexName = "orders-" + businessDate.format(INDEX_MONTH);
    IndexCoordinates coordinates = IndexCoordinates.of(indexName);

    return operations.get(id, Order.class, coordinates);
}
```

A document's ID only needs to be unique within an index. Two different indexes can contain documents with the same `_id`. Therefore, having only the ID is not always enough to locate a document; the application needs to know the index or have a suitable search strategy.

If the order creation date is unknown, you can search across an alias or a suitable set of indexes rather than guessing a monthly index.

## 5. Searching on an Index Selected at Runtime

You can also specify the target index for the Search API:

```java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public SearchHits<Order> searchOrders(
        Query query,
        String tenantIndex) {

    IndexCoordinates coordinates = IndexCoordinates.of(tenantIndex);

    return operations.search(query, Order.class, coordinates);
}
```

Here:

- `Query` describes search criteria.
- `Order.class` specifies the Java type for converting results.
- `IndexCoordinates` specifies the index or indexes to search.

You can run the same query across multiple indexes if mappings are compatible:

```java
IndexCoordinates coordinates = IndexCoordinates.of(
    "orders-2026-10",
    "orders-2026-11",
    "orders-2026-12"
);

SearchHits<Order> hits =
    operations.search(query, Order.class, coordinates);
```

Or use an index pattern if the API and Elasticsearch permissions allow it:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-2026-*");
```

Querying multiple indexes requires attention to mapping consistency. If the same field has different types across indexes, queries, sorting, or aggregations may fail or yield unexpected results. When needing to search across multiple indexes, maintain compatible mappings or use well-managed aliases.

## 6. Combining Entity Metadata and `IndexCoordinates`

An entity can still declare standard metadata:

```java
@Document(indexName = "orders")
public class Order {
    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String customerId;

    @Field(type = FieldType.Double)
    private Double total;
}
```

In a service, you can use the class metadata to convert the object while selecting the target index via coordinates:

```java
IndexCoordinates target = IndexCoordinates.of("orders-2026-11");

Order saved = operations.save(order, target);
```

The two components have distinct responsibilities:

| Component | Responsibility |
|---|---|
| `@Document` | Declares entity metadata, such as default index name and mapping options. |
| `@Id`, `@Field` | Describes how Java properties map to document IDs and fields. |
| `IndexCoordinates` | Specifies the target index for a particular operation. |
| `ElasticsearchOperations` | Executes save, get, search, delete, and other operations. |

Do not confuse the default index name in the annotation with the index passed to an overload accepting `IndexCoordinates`. When calling an explicit overload, coordinates determine the target of that operation.

## 7. Repositories and Limitations with Dynamic Indexes

Spring Data Elasticsearch repositories are very convenient when an entity has a single stable logical index:

```java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
```

Methods such as `save`, `findById`, and `findAll` use `Order`'s mapping metadata. Standard repositories do not offer an `IndexCoordinates` parameter per invocation.

If routing by tenant or time is required, you can keep repositories for operations on fixed indexes and create a dedicated service using `ElasticsearchOperations` for dynamic flows. Example:

```java
@Service
public class TenantOrderService {

    private final ElasticsearchOperations operations;

    public TenantOrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order save(String tenantId, Order order) {
        String indexName = "orders-" + validateTenantId(tenantId);
        return operations.save(
            order,
            IndexCoordinates.of(indexName)
        );
    }

    private String validateTenantId(String tenantId) {
        if (tenantId == null || !tenantId.matches("[a-z0-9-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenant id");
        }
        return tenantId;
    }
}
```

This illustrates tenant-based routing. Real applications must obtain the tenant from an authenticated identity and user permissions, then verify whether the tenant falls within authorized scope. Never trust an arbitrary tenant string sent by a client.

There is no need to create a separate Java repository per tenant. You can use a single shared service and pass a validated target index. This reduces bean count and avoids tying repository configuration to the number of tenants.

## 8. Creating Indexes and Mappings When Using `IndexCoordinates`

`IndexCoordinates` specifies an index name, but does not guarantee that index already exists. If the application writes to an index that has not been created yet, the outcome depends on Elasticsearch's auto-create configuration and account permissions; do not rely on Elasticsearch auto-creating indexes with default mappings.

A dynamic index management workflow typically requires:

1. Construct a valid index name.
2. Check whether the index already exists.
3. If not, create the index with the right settings and mapping.
4. Write the document using `ElasticsearchOperations` with `IndexCoordinates`.

Example outline for checking/creating an index:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-2026-11");
IndexOperations indexOps = operations.indexOps(coordinates);

if (!indexOps.exists()) {
    indexOps.create();
}
```

The snippet above only illustrates checking and creating an index. In real applications, establish the mapping before writing data. You can generate the mapping from entity metadata and send it to `IndexOperations` bound to the target coordinates, depending on the API of the Spring Data version in use:

```java
Document mapping = operations.indexOps(Order.class).createMapping();

IndexOperations targetIndexOps = operations.indexOps(coordinates);
if (!targetIndexOps.exists()) {
    targetIndexOps.create();
    targetIndexOps.putMapping(mapping);
}
```

In the example, the mapping is generated from the `Order` entity, while `targetIndexOps` operates on the dynamic index. Verify method signatures for your specific Spring Data version if the API differs. For production systems, index/mapping creation should usually be centrally managed or completed before write traffic begins.

### 8.1. Avoiding Race Conditions When Multiple Requests Create an Index Simultaneously

If multiple initial requests simultaneously check an index that does not exist yet, they may try to create it at the same time. One request succeeds while the others receive an index-already-exists error.

Do not treat that error as always fatal, nor blindly ignore every index creation error. Distinguish a "resource already exists" response from permission, mapping, connection, or configuration errors. A safer approach is to manage index creation through synchronized initialization, a migration job, or a dedicated provisioning component.

### 8.2. Do Not Rely on `@Document`'s `createIndex` for Every Dynamic Index

`@Document(createIndex = true)` is tied to entity metadata and the index resolved from that metadata. When code uses `IndexCoordinates` to write to multiple different indexes, do not assume the annotation will automatically create every dynamic index with its mapping.

Proactively manage the lifecycle for dynamic indexes, including settings, mappings, aliases, rollover, retention, and access permissions.

## 9. `IndexCoordinates` and Aliases

An alias is a logical name pointing to one or more physical indexes. Instead of exposing physical index names to the application, the application can operate through aliases:

```java
IndexCoordinates coordinates = IndexCoordinates.of("orders-write");
operations.save(order, coordinates);
```

For reading data, an alias can point to multiple indexes:

```java
IndexCoordinates readCoordinates = IndexCoordinates.of("orders-read");
SearchHits<Order> hits =
    operations.search(query, Order.class, readCoordinates);
```

This is helpful when data is partitioned by month yet the application needs to search across full history. Aliases decouple the logical name used by the application from physical index names.

Keep in mind:

- A write alias must have a clear write index if it points to multiple indexes.
- A read alias can point to multiple indexes, though their mappings should be compatible.
- Switching an alias to a new index must be performed in a controlled manner to prevent misdirected writes or missing read data.
- `IndexCoordinates` only carries the alias name; Elasticsearch determines which indexes that alias resolves to.

For time-series data, aliases combined with rollover and Index Lifecycle Management (ILM) are often easier to operate than calculating dated index names everywhere in code. Data streams are also a suitable option for append-oriented and time-series workloads.

## 10. Naming Rules for Dynamic Indexes

Index names are often composed of a prefix and an identifier such as tenant or month. Control the dynamic portion to prevent invalid names or unauthorized access outside intended data scope.

Example:

```java
String indexName = "orders-" + yearMonth;
IndexCoordinates coordinates = IndexCoordinates.of(indexName);
```

Rules:

- Use lowercase letters.
- Restrict allowed characters and length.
- Do not include spaces or characters forbidden by Elasticsearch in index names.
- Do not allow names starting with forbidden characters such as `-`, `_`, or `+`.
- Do not concatenate unvalidated data directly from HTTP requests.
- Do not let users pick wildcards arbitrarily if business rules disallow multi-index queries.
- Keep naming rules consistent across writing, reading, backups, and retention.

Example simple validator for the tenant part:

```java
private String validateTenantId(String tenantId) {
    if (tenantId == null || !tenantId.matches("[a-z0-9-]{1,40}")) {
        throw new IllegalArgumentException("Invalid tenant id");
    }
    return tenantId;
}
```

Then the application prepends a fixed prefix:

```java
String indexName = "orders-" + validateTenantId(tenantId);
```

This prevents users from passing an arbitrary index name or wildcard to access data outside their tenant. Format validation must still be paired with tenant authorization checks.

## 11. Choosing an Index Strategy by Problem

Having many tenants or large datasets does not automatically mean creating one index per tenant or per day. Each strategy carries its own operational cost.

| Strategy | Example | When Suitable | Considerations |
|---|---|---|---|
| Single fixed index | `orders` | Moderate data volume, uniform mapping and access control. | Simple; requires proper shard and lifecycle design. |
| Index per environment | `orders-dev`, `orders-prod` | Isolating data across environments. | Clear configuration, avoids writing to the wrong environment. |
| Time-based indexes | `orders-2026-11` | Continuously growing data, time-based retention needed. | Managing index count, mappings, and multi-index queries. |
| Index per tenant | `orders-tenant-a` | Need data isolation or per-tenant lifecycle. | Too many tenants can create too many shards/indexes and increase admin overhead. |
| Alias or data stream | `orders-read`, `orders-write` | Need stable logical names, rollover, or searching across multiple backing indexes. | Must manage aliases, write index, templates, and lifecycle. |

With a large number of tenants, a dedicated index per tenant can create numerous small shards and burden the cluster. Consider sharing an index with a tenant field and mandatory filters, or combining a partitioning strategy by tenant tiers. This decision involves security, capacity, load, and operational requirements—not just API syntax choices.

## 12. Common Mistakes

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Writes still go to default index despite tenant logic | Calling a repository or an overload without `IndexCoordinates`. | Check the actual method invoked and pass coordinates into the operation. |
| SpEL returns unexpected index name | Wrong property/profile or incorrect name-provider bean. | Check loaded properties, bean name, and when metadata was initialized. |
| Different tenants share the same index | Using a tenant context inside `@Document` expecting per-request evaluation. | Move tenant selection to a service and `IndexCoordinates`. |
| Dynamic index does not exist yet | Coordinates specify a name; they do not auto-create the index. | Provision index and mapping before writing. |
| Document saved yet search finds nothing | Reading from another index or alias does not point to new index yet. | Log target index, check aliases, and query directly. |
| Multi-index query throws mapping error | Same field has different types or structures. | Inspect each index's mapping and unify schemas. |
| Writing through alias fails | Alias points to multiple indexes without a designated write index. | Inspect alias and write index configuration. |
| Can access another tenant's index | Index name taken from input without authorization check. | Extract tenant from authenticated principal and enforce authorization in service. |
| Concurrent requests fail creating index | Race condition during check-and-create step. | Use synchronized provisioning or explicitly handle already-exists errors. |

When debugging, log the actual index or alias used by the request. Knowing the query is valid without knowing which index it ran against is insufficient to isolate the bug.

## 13. Comprehensive Example: Service Saving and Searching Orders by Month

The following example combines entity metadata, service index selection, and `IndexCoordinates`:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class MonthlyOrderService {

    private static final DateTimeFormatter MONTH_FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM");

    private final ElasticsearchOperations operations;

    public MonthlyOrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    private IndexCoordinates indexFor(LocalDate date) {
        String indexName = "orders-" + date.format(MONTH_FORMAT);
        return IndexCoordinates.of(indexName);
    }

    public Order save(Order order, LocalDate businessDate) {
        return operations.save(order, indexFor(businessDate));
    }

    public Order findById(String id, LocalDate businessDate) {
        return operations.get(id, Order.class, indexFor(businessDate));
    }

    public SearchHits<Order> search(
            Query query,
            LocalDate businessDate) {
        return operations.search(query, Order.class, indexFor(businessDate));
    }
}
```

Key design points:

- The index computation rule lives in one `indexFor` method, avoiding scattered name concatenation across multiple methods.
- The same `Order` entity is reused across multiple indexes.
- Each operation receives an explicit target index.
- The service is responsible for determining the business date and corresponding index.
- Each index's lifecycle and mapping must be appropriately provisioned prior to use.

In a real application, if you need to look up an order without knowing the month, you can consult a separate routing key, search via an alias, or query a bounded set of indexes. Avoid overly broad wildcards if datasets are large or access permissions prohibit them.

## 14. Summary of API Choices

| Requirement | How to Implement |
|---|---|
| One fixed index for the entity | `@Document(indexName = "orders")` |
| Index name from environment config at startup | Use property or SpEL in `@Document(indexName = ...)` |
| Select index by tenant per request | Compute validated name in service and use `IndexCoordinates.of(...)` |
| Select index by month/day | Compute index from business date and pass coordinates |
| Write or read through an alias | Pass alias name into `IndexCoordinates` |
| Search multiple indexes | Build coordinates with multiple names or a controlled pattern |
| Manage dynamic indexes | Use `IndexOperations` with coordinates, creating mappings and lifecycle intentionally |

SpEL expressions let entity metadata receive an index name from stable configuration. `IndexCoordinates` lets each operation choose its target index at runtime. When partitioning by tenant or time is needed, place index selection logic in a service, validate input, pass explicit coordinates, and manage indexes/mappings/aliases as part of the data lifecycle.
