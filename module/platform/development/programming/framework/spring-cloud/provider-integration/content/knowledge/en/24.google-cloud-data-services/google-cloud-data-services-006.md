# Reactive Firestore Repositories and Datastore Access via Their Corresponding Libraries

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot connects to managed services from AWS, Azure, and Google Cloud through their respective Spring Cloud libraries. For document data on Google Cloud, applications can use Firestore Native mode or Firestore in Datastore mode. Because the two modes have different APIs and data models, Spring provides two separate integration paths.

This lesson focuses on writing code and organizing the data access layer:

1. Choosing the right starter for the database mode.
2. Mapping Firestore POJOs with `@Document`, `@DocumentId`, and `@PropertyName`.
3. Building `FirestoreReactiveRepository` with `Mono`, `Flux`, query methods, and paging.
4. Composing reactive pipelines in services/WebFlux without blocking the event loop.
5. Using `FirestoreTemplate`/`FirestoreReactiveOperations` for queries and subcollections.
6. Using `ReactiveFirestoreTransactionManager` and `TransactionalOperator` for reactive transactions.
7. Mapping Datastore mode with `@Entity`, `@Id`, `@Field`, and `@Unindexed`.
8. Building `DatastoreRepository`, custom GQL, `DatastoreTemplate`, and transactions.
9. Understanding query, index, delete, and transaction limits of each integration.
10. Testing with emulators and verifying access permissions using the runtime identity.

> **Scope:** Examples reference Spring Framework on Google Cloud 8.2.1. The 8.x branch is compatible with Spring Boot 4.0/4.1; select a BOM matching your actual Spring Boot version. Firestore reactive repositories target Native mode. Spring Data Cloud Datastore targets Datastore mode and is incompatible with Native mode.

## 1. Two APIs, Two Repository Abstractions

### 1.1. Integration Architecture

~~~mermaid
flowchart TD
    SERVICE["Spring service layer"] --> NATIVE{"Database mode"}
    NATIVE -->|"Firestore Native"| F_REPO["FirestoreReactiveRepository"]
    NATIVE -->|"Datastore mode"| D_REPO["DatastoreRepository"]
    F_REPO --> F_TEMPLATE["FirestoreTemplate / FirestoreReactiveOperations"]
    D_REPO --> D_TEMPLATE["DatastoreTemplate"]
    F_TEMPLATE --> F_CLIENT["Firestore Java client"]
    D_TEMPLATE --> D_CLIENT["Datastore Java client"]
    F_CLIENT --> F_DB["Firestore Native database"]
    D_CLIENT --> D_DB["Firestore Datastore mode database"]
    ADC["ADC + runtime service account"] --> F_CLIENT
    ADC --> D_CLIENT
~~~

| Component | Firestore Native | Datastore mode |
| --- | --- | --- |
| Repository starter | spring-cloud-gcp-starter-data-firestore | spring-cloud-gcp-starter-data-datastore |
| Repository | FirestoreReactiveRepository<T> | DatastoreRepository<T, ID> |
| Primary return types | Reactor Mono<T>, Flux<T> | Java object, Iterable, List, Optional, Page, Slice |
| Template | FirestoreTemplate, FirestoreReactiveOperations | DatastoreTemplate, DatastoreOperations |
| Query | Firestore query API; derived query methods | Datastore query/GQL; derived query methods |
| Transaction | Reactive transaction manager/operator | DatastoreTransactionManager or performTransaction |
| Client bean | Firestore | Datastore |

Do not use one mode's repository to access the other mode. When a project has multiple databases or multiple integrations, explicitly configure database IDs and transaction managers to avoid connecting to the wrong target.

### 1.2. Choosing a Starter Based on Need

- Need Firestore Native and Spring Data reactive repositories/templates: use spring-cloud-gcp-starter-data-firestore.
- Need only the Firestore Java client without Spring Data: use spring-cloud-gcp-starter-firestore.
- Need Datastore mode and Spring Data repositories/templates: use spring-cloud-gcp-starter-data-datastore.
- Need the Datastore Java client directly: the Datastore starter still auto-configures the Datastore bean; you can inject this client in specialized services.

Do not add multiple starters simultaneously just to have multiple ways to call the database. Each starter can create its own client and transaction infrastructure; only add modules the application actually uses.

## 2. Dependencies and Common Configuration

### 2.1. Managing Versions with the BOM

In Maven, import the BOM once under dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Choose the spring-cloud-gcp.version value per the Spring Boot and Spring Framework on Google Cloud compatibility matrix. The examples below omit explicit versions because the BOM manages compatible modules:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-data-firestore</artifactId>
    </dependency>
</dependencies>
~~~

To use Datastore mode, replace the Firestore dependency with:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
</dependency>
~~~

If an application genuinely needs both modes, both starters can be declared. However, separate repository/entity packages, database IDs, configuration, and transaction boundaries to avoid mixing domain types or picking the wrong transaction manager.

### 2.2. ADC and Project ID

Both starters use Google Cloud core auto-configuration to resolve project ID and credentials. In local development, use Application Default Credentials. On Cloud Run, GKE, or Compute Engine, attach a service account/workload identity to the workload.

Example project configuration:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
~~~

Do not commit service account JSON keys into source code, images, or configuration files. Prefer runtime identity; only supply custom credentials via properties when explicitly required and securely managed.

## 3. Firestore Native: Configuration and Document Mapping

### 3.1. Configuring Firestore

Common properties:

| Property | Meaning |
| --- | --- |
| spring.cloud.gcp.firestore.enabled | Enables/disables Firestore auto-configuration |
| spring.cloud.gcp.firestore.project-id | Project containing the Firestore database |
| spring.cloud.gcp.firestore.database-id | Database ID; defaults to (default) |
| spring.cloud.gcp.firestore.emulator.enabled | Enables emulator connection |
| spring.cloud.gcp.firestore.host-port | Host/port of Firestore or the emulator |
| spring.cloud.gcp.firestore.credentials.location | Custom credentials if different from core configuration |
| spring.cloud.gcp.firestore.credentials.encoded-key | Base64-encoded JSON credentials if custom configuration is required |

Example production/local profile:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      firestore:
        project-id: rental-platform-dev
        database-id: "(default)"
        emulator:
          enabled: false
        host-port: firestore.googleapis.com:443
~~~

When using an already-running emulator, enable emulator.enabled and point host-port to the emulator's host/port. Do not enable the emulator in production.

### 3.2. Document POJO

Spring Data Cloud Firestore maps POJOs to collections/documents. Key annotations:

- @Document(collectionName = "..."): specifies the collection.
- @DocumentId: marks the document ID; this field must be of type String.
- @PropertyName: maps the persisted property name.
- @UpdateTime: receives the update timestamp managed by Firestore.

Example:

~~~java
import com.google.cloud.Timestamp;
import com.google.cloud.firestore.annotation.PropertyName;
import com.google.cloud.firestore.annotation.DocumentId;
import com.google.cloud.spring.data.firestore.Document;
import com.google.cloud.spring.data.firestore.mapping.UpdateTime;

import java.util.List;

@Document(collectionName = "orders")
public class OrderDocument {

    @DocumentId
    private String id;

    private String customerId;

    private String status;

    private Long totalAmount;

    private Timestamp createdAt;

    @UpdateTime(version = true)
    private Timestamp updateTime;

    private List<String> tags;

    public OrderDocument() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    @PropertyName("customer_id")
    public String getCustomerId() {
        return customerId;
    }

    @PropertyName("customer_id")
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Long getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(Long totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

If id is null, Firestore generates a document ID when the entity is saved. After a successful save, retain the returned ID on the entity so subsequent operations target the right document. Do not use Long for @DocumentId; Firestore mapping requires String.

@PropertyName can be placed on a public field or on getters/setters. When placed on accessors, apply it consistently to both getter and setter so serialization and deserialization use the same field name.

### 3.3. Data Types and Embedded Objects

Commonly supported types include String, Long, Integer, Double, Float, Boolean, Character, Date, Map, List, Enum, com.google.cloud.Timestamp, GeoPoint, and Blob.

Custom POJOs and lists of custom POJOs are stored as embedded maps/arrays. Example:

~~~java
public class ShippingAddress {

    private String street;
    private String city;
    private String country;

    public ShippingAddress() {
    }

    // Getters and setters.
}

@Document(collectionName = "orders")
public class OrderDocument {

    @DocumentId
    private String id;

    private ShippingAddress shippingAddress;

    private List<ShippingAddress> previousAddresses;

    public OrderDocument() {
    }
}
~~~

Embedded objects fit small data typically read alongside the parent document. For unbounded lists, independent queries, or separate lifecycles, use a subcollection instead of an ever-growing array.

### 3.4. Controlling Update Timestamps

Firestore automatically manages the update time for a document. An @UpdateTime field receives that timestamp after a write operation. When using @UpdateTime(version = true), Spring Data adds a precondition ensuring the document has not changed since it was last read.

This provides document-level optimistic locking. If two requests read the same version and both write, the second request can be rejected because the version no longer matches. Handle conflicts by re-reading and deciding at the business layer; do not blindly retry a value computed from a stale snapshot.

## 4. FirestoreReactiveRepository

### 4.1. Declaring the Repository

Spring Data Cloud Firestore provides FirestoreReactiveRepository<T>, extending the reactive CRUD repository:

~~~java
import com.google.cloud.spring.data.firestore.FirestoreReactiveRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderDocumentRepository
        extends FirestoreReactiveRepository<OrderDocument> {

    Flux<OrderDocument> findByCustomerId(String customerId);

    Flux<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);

    Flux<OrderDocument> findByStatusOrderByCreatedAtDesc(String status);

    Flux<OrderDocument> findByTotalAmountGreaterThan(Long minimum);

    Mono<OrderDocument> findFirstByCustomerIdAndStatus(
            String customerId, String status);

    Mono<Long> countByStatus(String status);
}
~~~

The repository needs no manual implementation. The Spring Boot starter enables reactive repository scanning automatically. If you need to customize scan packages, use @EnableReactiveFirestoreRepositories.

### 4.2. What Do Mono and Flux Express?

| Return type | Meaning | Example |
| --- | --- | --- |
| Mono<OrderDocument> | Zero or one document | findById, findFirstBy... |
| Flux<OrderDocument> | Zero or many documents | findByStatus, findAll |
| Mono<Long> | A single count value | countByStatus |
| Mono<Void> | Completes without returning a payload | deleteById, service command |

Reactive repositories return publishers. Database calls are typically executed when the publisher is subscribed to, so calling a method only builds the pipeline; it does not necessarily execute the query yet.

In WebFlux, controllers/services should return Mono/Flux directly so the runtime schedules execution. Do not call block() on a request path, as that blocks the thread handling the reactive pipeline.

### 4.3. CRUD in Services

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderDocumentService {

    private final OrderDocumentRepository repository;

    public OrderDocumentService(OrderDocumentRepository repository) {
        this.repository = repository;
    }

    public Mono<OrderDocument> create(OrderDocument order) {
        return repository.save(order);
    }

    public Mono<OrderDocument> findById(String id) {
        return repository.findById(id);
    }

    public Mono<Void> delete(String id) {
        return repository.deleteById(id);
    }
}
~~~

Write semantics note: the current FirestoreTemplate.save API has insert-only behavior; saveAll writes with insert/update semantics and is not atomic across the whole publisher. When calling via a repository, check the implementation of your exact BOM and do not assume ReactiveCrudRepository.save has JPA-style upsert semantics. If you need to update an existing document, use saveAll for a single operation with optimistic locking or the native client update/set merge; test preconditions before deploying. Do not assume save behaves like DatastoreTemplate's upsert.

### 4.4. Composing Multiple Reactive Operations

Example creating an order and reading it back:

~~~java
public Mono<OrderDocument> createAndReload(OrderDocument order) {
    return repository.save(order)
            .flatMap(saved -> repository.findById(saved.getId()));
}
~~~

Example finding an order, checking status, and upserting the document via saveAll:

~~~java
public Mono<Void> markPacked(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                if (!"PAID".equals(order.getStatus())) {
                    return Mono.error(
                            new IllegalStateException("Order is not paid"));
                }

                order.setStatus("PACKED");
                return repository.saveAll(Mono.just(order)).then();
            });
}
~~~

This example illustrates composing publishers; saveAll is not atomic when emitting multiple documents. An @UpdateTime(version = true) field in the entity can help detect documents modified by another request. If multiple changes must commit together, use the transaction API and only use operations verified to participate in the transaction context. Checking status in an independent query and writing in a subsequent request can create a race condition.

### 4.5. Error Handling

Use Reactor operators to translate errors at appropriate boundaries:

~~~java
public Mono<OrderDocument> findOrCreate(String id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.defer(() -> {
                OrderDocument order = new OrderDocument();
                order.setId(id);
                order.setStatus("PENDING");
                return repository.save(order);
            }));
}
~~~

switchIfEmpty handles the missing-document case; it does not handle permission denied, timeouts, or network errors. Use onErrorMap to convert exceptions into domain exceptions and onErrorResume when a safe fallback exists.

Do not turn every database error into an empty result. Doing so can cause the API to return 404 for an IAM error or outage.

## 5. Firestore Query Methods

### 5.1. Deriving Queries from Method Names

Spring Data maps method names to Firestore queries. Examples:

~~~java
Flux<OrderDocument> findByStatus(String status);

Flux<OrderDocument> findByCustomerIdAndStatus(
        String customerId, String status);

Flux<OrderDocument> findByCreatedAtGreaterThan(Timestamp timestamp);

Flux<OrderDocument> findByTagsContains(String tag);

Flux<OrderDocument> findByStatusOrderByCreatedAtDesc(String status);

Mono<OrderDocument> findTopByCustomerIdOrderByCreatedAtDesc(
        String customerId);
~~~

You can use nested property expressions to filter fields inside embedded objects—for example, findByShippingAddressCity(String city)—if the corresponding mapping and query type are supported by Firestore.

### 5.2. Filter Limits in Repository Methods

Per the Spring Framework on Google Cloud 8.2.1 reference, Firestore query methods support filters combined with AND:

- Equality and not-equal.
- Greater than/greater than or equal.
- Less than/less than or equal.
- Is null.
- Contains.
- In and not-in.

contains accepts a single value or a list of at most 10 elements. in and not-in accept lists of at most 10 elements. When combining in with contains, the argument to contains must be a single value.

These are limits of Spring Data query methods. The Firestore API offers additional query expressions, which does not mean all of them can be generated from repository method names.

In reference 8.2.1, Spring Data Cloud Firestore does not yet support query by example, projections, or auditing. If these capabilities are needed, use the query builder/native client or implement mapping/auditing at the application layer.

### 5.3. No GQL @Query for Native Mode

Firestore Native has no GQL/SQL query language equivalent to Datastore. Therefore, GQL-style custom @Query is not supported. When derived query methods are not expressive enough, use FirestoreTemplate or the Firestore Java client query builder.

Do not try to write @Query("SELECT ...") as in a Datastore repository; that is not valid Firestore Native syntax.

### 5.4. Indexes and Query Failures

Queries combining filters and sorts may require a composite index. When an index is missing, Firestore typically returns an error containing an index creation link. Proper workflow:

1. Reproduce the query in dev/emulator or sandbox.
2. Read the suggested index definition.
3. Review field order, sort direction, and collection scope.
4. Add the index to deployment configuration.
5. Monitor build status before releasing the query.

Do not add indexes to every field. Indexes increase write and storage costs; create them only for real query patterns.

### 5.5. Paging and Limiting Results

Repositories can accept Pageable to apply limits and pagination, for example:

~~~java
Flux<OrderDocument> findByStatus(
        String status, Pageable pageable);
~~~

Pageable supplies offset/page size and sorting; the return type remains Flux, not a Page with total page counts. If a total count is needed, invoke count separately and weigh the cost.

For large collections, prefer bounded page sizes and cursor/keyset strategies. Deep offsets can be expensive, and results can shift when documents are added or deleted between page requests.

## 6. FirestoreTemplate and FirestoreReactiveOperations

### 6.1. When to Use the Template?

Repositories fit CRUD and stable query methods. Use the template when you need:
- Dynamic queries built from multiple conditions.
- Subcollection operations.
- Firestore APIs not exposed by repositories.
- DTO conversions or custom processing over a set of documents.
- Structuring read/write operations inside transactions.

The Spring Boot starter auto-configures FirestoreTemplate, FirestoreReactiveOperations, and the Firestore bean for low-level Java client access.

### 6.2. Saving and Reading with the Template

Example using reactive operations:

~~~java
import com.google.cloud.spring.data.firestore.FirestoreReactiveOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class OrderTemplateService {

    private final FirestoreReactiveOperations firestore;

    public OrderTemplateService(FirestoreReactiveOperations firestore) {
        this.firestore = firestore;
    }

    public Mono<OrderDocument> save(OrderDocument order) {
        return firestore.save(order);
    }

    public Flux<OrderDocument> findAll() {
        return firestore.findAll(OrderDocument.class);
    }

    public Mono<Long> deleteAll() {
        return firestore.deleteAll(OrderDocument.class);
    }
}
~~~

FirestoreTemplate is the template implementation configured by the starter. Depend on the FirestoreReactiveOperations interface in services so code relies on an abstraction.

With FirestoreOperations, save(entity) is insert-only; saveAll(publisher) supports insert/update but uses buffering and is not atomic across the entire publisher. Hence, do not treat saveAll as a batch transaction.

Cost note: the 8.0.4 API reference describes FirestoreTemplate's count as reading document IDs and counting them, rather than an optimized aggregation count. Before calling count on a large collection, check the implementation in your BOM and consider Firestore aggregation queries or maintaining business counters.

### 6.3. Subcollections with withParent

To work with a subcollection attached to a parent, create an operations object via withParent:

~~~java
FirestoreReactiveOperations itemOperations =
        firestore.withParent(orderDocument);

return itemOperations.save(orderItem);
~~~

The parent must have a non-empty ID; the parent document does not necessarily have to exist prior to manipulating children. You can then save, query, and delete children through this operations object.

Deleting a parent document does not automatically delete subcollections. If the business requires cascade deletion, implement an explicit child deletion workflow with bounded batches, retries, and resume capability.

### 6.4. Native Firestore Java Client

The Firestore data starter also configures a Firestore bean. When specialized APIs are needed, you can use it directly:

~~~java
import com.google.cloud.firestore.Firestore;
import com.google.api.core.ApiFuture;
import com.google.cloud.firestore.DocumentSnapshot;

public class NativeOrderReader {

    private final Firestore firestore;

    public NativeOrderReader(Firestore firestore) {
        this.firestore = firestore;
    }

    public ApiFuture<DocumentSnapshot> get(String orderId) {
        return firestore.collection("orders")
                .document(orderId)
                .get();
    }
}
~~~

The native client returns ApiFuture, not Mono/Flux. Calling get() on the future inside the WebFlux event loop blocks the thread. Wait on the future only in synchronous applications or offload to an appropriate scheduler; better yet, use the reactive template when request paths require non-blocking I/O.

## 7. Reactive Transactions in Firestore

### 7.1. ReactiveFirestoreTransactionManager

Spring Framework on Google Cloud provides ReactiveFirestoreTransactionManager. You can create a TransactionalOperator to wrap a chain of reactive operations:

~~~java
import com.google.cloud.spring.data.firestore.transaction.ReactiveFirestoreTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;

public class FirestoreTransactionConfig {

    public TransactionalOperator firestoreTransactionOperator(
            ReactiveFirestoreTransactionManager transactionManager) {

        DefaultTransactionDefinition definition =
                new DefaultTransactionDefinition();

        definition.setReadOnly(false);

        return TransactionalOperator.create(
                transactionManager, definition);
    }
}
~~~

The Spring Boot starter auto-configures the reactive transaction manager. You can inject the manager and construct the operator in a service or configuration class; there is no need to manually create a Firestore gRPC stub.

### 7.2. Wrapping a Repository Operation Chain

~~~java
public Mono<Void> createOrderAndAudit(
        OrderDocument order,
        OrderAuditDocument audit,
        TransactionalOperator transactionOperator) {

    return orderRepository.save(order)
            .then(auditRepository.save(audit))
            .then()
            .as(transactionOperator::transactional);
}
~~~

Write operations in the transaction commit atomically. If one operation fails, the transaction rolls back. In a read-write transaction, perform all reads before starting writes; do not interleave reads after writes.

### 7.3. Read First, Write After

A transaction can read current state and then write related documents:

~~~java
public Mono<Void> recordConfirmationRequest(
        String orderId,
        TransactionalOperator transactionOperator) {

    Mono<Void> work = orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                if (!"PENDING".equals(order.getStatus())) {
                    return Mono.error(
                            new IllegalStateException("Invalid order state"));
                }

                OrderAuditDocument audit = new OrderAuditDocument();
                audit.setOrderId(orderId);
                audit.setAction("CONFIRM_REQUESTED");
                return auditRepository.save(audit).then();
            });

    return work.as(transactionOperator::transactional);
}
~~~

This example illustrates reading an order and then inserting an audit document within the same reactive transaction. Since the audit has a new ID, the insert-only save fits well. If you need to update the order and audit atomically, use the Firestore transaction API with write operations verified to participate in the same transaction; do not assume batched saveAll is atomic. Do not call payment gateways, send emails, or publish messages inside a transaction; transactions can retry or roll back.

### 7.4. @Transactional and Reactive Transactions

Spring Framework on Google Cloud 8.2.1 documents both TransactionalOperator with ReactiveFirestoreTransactionManager and declarative @Transactional for Firestore repositories/templates. The declarative transaction section in the reference mentions the SpannerTransactionManager bean, while the reactive transaction section uses ReactiveFirestoreTransactionManager.

For reactive pipelines, prefer ReactiveFirestoreTransactionManager with TransactionalOperator as shown above so transaction boundaries are explicit. If choosing @Transactional, verify the actual transaction manager bean and BOM compatibility before applying; do not assume Spanner's or Datastore's manager can manage Firestore.

## 8. Datastore Mode: Configuration and Entity Mapping

### 8.1. Starter and Properties

Use the starter:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
</dependency>
~~~

Common properties:

| Property | Meaning |
| --- | --- |
| spring.cloud.gcp.datastore.enabled | Enables/disables Datastore client |
| spring.cloud.gcp.datastore.project-id | Project containing the database |
| spring.cloud.gcp.datastore.database-id | Database ID; defaults to (default) |
| spring.cloud.gcp.datastore.namespace | Default namespace |
| spring.cloud.gcp.datastore.host | Host/port of service or standalone emulator |
| spring.cloud.gcp.datastore.emulator.enabled | Auto-starts the Datastore Emulator |
| spring.cloud.gcp.datastore.emulator.port | Emulator port; defaults to 8081 |
| spring.cloud.gcp.datastore.emulator.consistency | Consistency setting for the emulator |
| spring.cloud.gcp.datastore.skip-null-value | Skips properties with null values on write |

Example:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      datastore:
        project-id: rental-platform-dev
        database-id: "(default)"
        namespace: orders
        emulator:
          enabled: false
~~~

If the autoconfigured emulator is enabled, spring.cloud.gcp.datastore.host is ignored and the starter connects to its managed local emulator. If you run the emulator yourself, set host to the exact address.

### 8.2. Datastore Entities

Key mapping annotations:

- @Entity(name = "..."): kind name.
- @Id: ID/key property; every entity must have one ID.
- @Field(name = "..."): property name in Datastore.
- @Transient: ignores the field during reads/writes.
- @Unindexed: skips creating indexes for properties not needing queries.

Example:

~~~java
import com.google.cloud.spring.data.datastore.core.mapping.Entity;
import com.google.cloud.spring.data.datastore.core.mapping.Field;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

@Entity(name = "orders")
public class DatastoreOrder {

    @Id
    private Long id;

    @Field(name = "customer_id")
    private String customerId;

    private String status;

    private Long totalAmount;

    @Transient
    private String displayLabel;

    public DatastoreOrder() {
    }

    // Getters and setters.
}
~~~

If Long id is null when saved, Datastore can allocate a numeric ID and Spring Data populates it back onto the entity. Do not use primitive long if you want auto-generated IDs, because the default value 0 is not null.

### 8.3. Keys and Relationships

Datastore mode uses Key as the identifier. The ID property can be String, Long, or Key depending on the model. For ancestor paths, use Key to preserve full kind, identifier, and ancestor details.

Spring Data Datastore relationships:

- Embedded entity: child object stored inside the parent entity.
- @Descendants: child entities under the parent entity's ancestor path.
- @Reference: stores a key to an entity of another kind.
- @LazyReference: defers resolving the referenced entity.

Example child entity with an ancestor key:

~~~java
import com.google.cloud.datastore.Key;
import com.google.cloud.spring.data.datastore.core.mapping.Entity;
import org.springframework.data.annotation.Id;

@Entity(name = "orderItems")
public class DatastoreOrderItem {

    @Id
    private Key id;

    private String productId;

    private Long quantity;

    public DatastoreOrderItem() {
    }
}
~~~

Do not use namespaces as a security boundary. If a namespace represents a tenant, the service must still verify tenant identity and restrict access at the application layer.

## 9. DatastoreRepository

### 9.1. Declaring the Repository

DatastoreRepository<T, ID> extends PagingAndSortingRepository and adds Datastore-specific operations:

~~~java
import com.google.cloud.spring.data.datastore.repository.DatastoreRepository;
import java.util.List;
import java.util.Optional;

public interface DatastoreOrderRepository
        extends DatastoreRepository<DatastoreOrder, Long> {

    List<DatastoreOrder> findByCustomerId(String customerId);

    List<DatastoreOrder> findByCustomerIdAndStatus(
            String customerId, String status);

    Optional<DatastoreOrder> findFirstByCustomerIdAndStatus(
            String customerId, String status);

    int countByStatus(String status);

    boolean existsByCustomerId(String customerId);
}
~~~

The Spring Boot starter configures repository scanning automatically. If you need to customize packages or repository behavior, use @EnableDatastoreRepositories.

### 9.2. Derived Query Methods

Spring Data Cloud Datastore supports derived filter methods including:
- Equality.
- Not equal.
- Greater than/greater than or equal.
- Less than/less than or equal.
- Is null.

Filters in derived query methods are combined with AND. Do not assume full Spring Data JPA operators, OR, JOINs, or arbitrary SQL expressions are available.

When other queries are needed, use custom GQL or the Datastore Java client. Verify composite indexes before deploying new queries.

### 9.3. Empty Results and Return Types

Use Optional<T> for results that may not exist. Methods returning collections do not return null; when no entities match, the collection is empty.

Example:

~~~java
Optional<DatastoreOrder> findFirstByCustomerIdAndStatus(
        String customerId, String status);
~~~

Avoid methods returning a single object without clearly defining not-found behavior. If the business API expects 404, convert Optional.empty() into a domain exception at the service/controller boundary.

### 9.4. Paging, Slice, and Page

Datastore repositories support Pageable, Sort, Page, and Slice.

~~~java
Page<DatastoreOrder> findByStatus(
        String status, Pageable pageable);

Slice<DatastoreOrder> findByCustomerId(
        String customerId, Pageable pageable);
~~~

Page requires an extra query to compute total elements/pages. Slice skips the count query and is usually more efficient when you only need to know whether a next page exists.

Datastore queries support offset/limit, though deep offsets can be expensive. For large datasets, design cursor/keyset pagination by key/index and cap page sizes.

### 9.5. An Important Limitation of Delete Queries

Methods such as deleteByStatus or removeByCustomerId execute in two steps: query the entities and then delete the matched entities. They do not run as an atomic delete statement inside a transaction. Due to query restrictions inside Datastore transactions, these derived delete queries cannot be used inside @Transactional or performTransaction.

If you need atomic read/check-then-delete, design the transaction within the ancestor/query constraints supported by Datastore or operate directly by key inside a transaction. Do not rely on deleteBy... for multi-step atomic workflows.

## 10. Custom GQL with @Query

### 10.1. When to Use Custom GQL?

Derived method names fit simple filters. Use @Query when you need explicit GQL control, key selection, or projections.

Example:

~~~java
import com.google.cloud.spring.data.datastore.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface DatastoreOrderGqlRepository
        extends DatastoreRepository<DatastoreOrder, Long> {

    @Query("SELECT * FROM orders WHERE customer_id = @customer")
    List<DatastoreOrder> findByCustomer(
            @Param("customer") String customerId);
}
~~~

The placeholder name after `@` must match `@Param`. Always bind parameters; never concatenate user input into GQL.

### 10.2. Querying Keys

Datastore GQL provides the special `__key__` column to fetch keys:

~~~java
import com.google.cloud.datastore.Key;

@Query("SELECT __key__ FROM orders WHERE status = @status")
List<Key> findKeysByStatus(@Param("status") String status);
~~~

When comparing IDs in custom queries, use `__key__` and a Key parameter if the query requires a full key. Keys can be constructed via `DatastoreTemplate.createKey(...)`.

### 10.3. Count and Exists

With custom GQL, `@Query` supports `count = true` or `exists = true` for cases needing a count or boolean. Choose matching return types:

~~~java
@Query(value = "SELECT __key__ FROM orders WHERE status = @status",
       count = true)
int countOrdersByStatus(@Param("status") String status);
~~~

~~~java
@Query(value = "SELECT __key__ FROM orders WHERE customer_id = @customer",
       exists = true)
boolean hasOrders(@Param("customer") String customerId);
~~~

Select `__key__` when only keys or counts are needed to avoid fetching entire entities. Verify syntax and indexes in tests before deploying.

### 10.4. Projections

Spring Data Cloud Datastore supports interface projections:

~~~java
public interface OrderSummary {
    String getCustomerId();
    String getStatus();
}

public interface DatastoreOrderSummaryRepository
        extends DatastoreRepository<DatastoreOrder, Long> {

    List<OrderSummary> findByStatus(String status);
}
~~~

Projections reduce mapping overhead when only a few fields are needed. For custom GQL selecting specific properties, Datastore requires a composite index containing the projected fields per service rules; verify indexes before release.

## 11. DatastoreTemplate and DatastoreOperations

### 11.1. When to Use the Template?

Use DatastoreTemplate when you need:
- Reading by ID/key or multiple IDs.
- Fetching all entities of a kind.
- GQL queries returning entities or keys.
- Creating keys.
- Writing maps directly.
- Executing transactions via performTransaction.

The Spring Boot starter auto-configures the DatastoreTemplate bean, the DatastoreOperations interface, and the Datastore client.

### 11.2. Reading by ID and Writing Entities

~~~java
import com.google.cloud.spring.data.datastore.core.DatastoreTemplate;
import org.springframework.stereotype.Service;

@Service
public class DatastoreOrderService {

    private final DatastoreTemplate datastore;

    public DatastoreOrderService(DatastoreTemplate datastore) {
        this.datastore = datastore;
    }

    public DatastoreOrder find(Long id) {
        return datastore.findById(id, DatastoreOrder.class);
    }

    public DatastoreOrder save(DatastoreOrder order) {
        return datastore.save(order);
    }
}
~~~

Other common operations:

~~~java
DatastoreOrder one =
        datastore.findById(orderId, DatastoreOrder.class);

List<DatastoreOrder> many =
        datastore.findAllById(orderIds, DatastoreOrder.class);

List<DatastoreOrder> all =
        datastore.findAll(DatastoreOrder.class);
~~~

save has update-or-insert semantics. insert fails if the entity already exists. The API does not currently support partial updates writing only a subset of properties; write operations persist the POJO's properties. If you only want to change a single field, design entity/update flows carefully or use an appropriate lower-level client.

### 11.3. Querying with DatastoreTemplate

DatastoreTemplate supports GQL/query objects and entity mapping. Example using the Datastore client query builder:

~~~java
import com.google.cloud.datastore.Entity;
import com.google.cloud.datastore.Query;
import com.google.cloud.datastore.StructuredQuery;

Query<Entity> query = Query.newEntityQueryBuilder()
        .setKind("orders")
        .setFilter(StructuredQuery.PropertyFilter.eq(
                "status", "PAID"))
        .build();

Iterable<DatastoreOrder> orders =
        datastore.query(query, DatastoreOrder.class);
~~~

This illustrates the Datastore client query builder; imports and generic query types must match the client version managed by the BOM. When only GQL is needed, you can use `@Query` on repositories. For dynamic queries, the lower-level Datastore client lets you build query objects directly.

### 11.4. Transactions with DatastoreTemplate

DatastoreOperations.performTransaction supplies a DatastoreOperations instance bound to the transaction:

~~~java
public void markPaid(Long orderId) {
    datastore.performTransaction(transactionDatastore -> {
        DatastoreOrder order = transactionDatastore.findById(
                orderId, DatastoreOrder.class);

        if (order == null) {
            throw new IllegalArgumentException("Order not found");
        }

        order.setStatus("PAID");
        transactionDatastore.save(order);
        return null;
    });
}
~~~

Do not open nested transactions inside the transaction callback. Datastore has consistency/ancestor constraints for queries inside transactions; design transactional operations around keys/ancestors supported by the service.

### 11.5. @Transactional and Transaction Manager

The Datastore starter provides DatastoreTransactionManager. Repositories and templates can participate in declarative transactions:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Service
public class DatastoreOrderApplicationService {

    private final DatastoreOrderRepository repository;

    public DatastoreOrderApplicationService(
            DatastoreOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "datastoreTransactionManager")
    public void updateOrder(Long id) {
        DatastoreOrder order = repository.findById(id).orElseThrow();
        order.setStatus("PAID");
        repository.save(order);
    }
}
~~~

If the application also uses Firestore or Spanner, specify the transaction manager so Spring does not choose the wrong bean. Do not call performTransaction inside a method already annotated with @Transactional on the same Datastore database.

## 12. Comparing Repository, Template, and Client Choices

| Scenario | Firestore Native | Datastore mode |
| --- | --- | --- |
| Common CRUD | FirestoreReactiveRepository | DatastoreRepository |
| Simple query methods | Reactive query methods | Synchronous query methods |
| Custom queries | FirestoreTemplate or native query builder | GQL @Query or DatastoreTemplate |
| Subcollections | FirestoreReactiveOperations.withParent | Ancestor/descendant or reference |
| Reactive transactions | ReactiveFirestoreTransactionManager + TransactionalOperator | Do not use reactive API; use Datastore transactions |
| Direct client API | Firestore + ApiFuture | Datastore client |
| Paging | Pageable parameter and Flux | Page, Slice, Pageable, Sort |
| Query annotation | Custom @Query not supported | Supports GQL @Query |

Selection guidelines:

- Use repositories when queries are stable, simple, and fit method convention limits.
- Use templates when you need dynamic queries, subcollections, transactions, or specialized Spring abstraction APIs.
- Use the native client when you need capabilities not exposed by templates/repositories.
- Keep synchronous Datastore APIs behind synchronous service boundaries; keep Firestore reactive end-to-end across the WebFlux pipeline.

## 13. Security and Operations

### 13.1. IAM by Runtime Identity

Spring Boot servers use ADC and IAM. Grant minimal roles to the service account:
- Datastore/Firestore user role for read/write workloads.
- Viewer/read-only role for read-only workloads.
- Separate migration/index administration principals from runtime APIs.

With Firestore Native server SDKs, requests use IAM and server client libraries bypass Firestore Security Rules. Security Rules protect mobile/web client SDKs; the backend must still enforce user/tenant authorization.

### 13.2. Do Not Block the Reactive Event Loop

In Firestore reactive paths:
- Do not call block() in controllers/services.
- Do not call ApiFuture.get() on the event loop.
- Use Mono/Flux throughout the pipeline.
- Offload to a blocking scheduler only when forced to call a synchronous library.
- Bound concurrency and page sizes.

In Datastore mode, repositories/templates are synchronous APIs. If the application uses WebFlux, offload blocking operations to an appropriate scheduler or consider synchronous endpoints/services matching your stack. Do not assume DatastoreRepository becomes non-blocking merely because a controller returns Mono.

### 13.3. Indexes and Latency

Monitor:
- Query latency p50/p95/p99.
- Documents/entities read compared to returned count.
- Composite indexes missing/building.
- Error rates by operation.
- Transaction conflicts/aborts.
- Session/thread usage and blocking time.
- Differences between emulator and production behavior.

Use projections/field selection where possible. Avoid unbounded findAll() on large collections/kinds; use paging/cursors, filters, and indexed sorts.

### 13.4. Data Deletion and Retention

Firestore subcollections do not automatically cascade when deleting a parent. Datastore descendants/references have different semantics and can trigger recursive reads/writes through mapping. Explicitly define retention, soft deletes, cascade cleanup, and resume capability.

Do not run bulk deletion in production via unbounded deleteAll() calls. Split into batches, rate-limit, and audit results.

## 14. Testing with Emulators

### 14.1. Firestore Emulator

Firestore Native uses the Firebase Emulator. When the emulator runs on default port 8080, configure:

~~~yaml
spring:
  cloud:
    gcp:
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
~~~

You can use Testcontainers FirestoreEmulatorContainer in CI. Test repository CRUD, queries, embedded mappings, transactions, subcollections, and optimistic locking.

### 14.2. Datastore Emulator

The Datastore starter can auto-start the emulator:

~~~yaml
spring:
  cloud:
    gcp:
      datastore:
        emulator:
          enabled: true
          port: 8081
          consistency: 0.9
~~~

The emulator is useful for mappings, GQL, repositories, CRUD, and basic transactions. You can use a self-started emulator by setting spring.cloud.gcp.datastore.host.

### 14.3. Testing Reactive Flows with StepVerifier

Do not call block() to test every pipeline when Reactor Test can be used:

~~~java
StepVerifier.create(orderRepository.findByStatus("PAID"))
        .expectNextMatches(order -> "PAID".equals(order.getStatus()))
        .thenCancel()
        .verify();
~~~

When checking an entire collection, use expectNextCount, expectNextMatches, or collectList in pipeline tests. Always verify error and completion signals, not just a single emitted value.

### 14.4. Testing Datastore Repositories

Verify:
- Entity mappings and auto-generated IDs.
- save upsert and insert duplicate behavior.
- Derived query methods with AND filters.
- Custom GQL parameter binding.
- Page and Slice.
- Transaction commits/rollbacks.
- Delete query boundaries.
- Required indexes.

Emulators do not replace a real sandbox for verifying IAM, index provisioning, quotas, concurrency, and network paths.

## 15. Common Errors and How to Handle Them

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| Cannot create Firestore repository | Missing starter or wrong package scan | Check dependencies and @EnableReactiveFirestoreRepositories |
| @DocumentId mapping error | ID is not String or missing annotation | Use String and a single @DocumentId field |
| Reactive endpoint hangs | block() or ApiFuture.get() on event loop | Keep publishers reactive or offload blocking to scheduler |
| Firestore query demands index | Missing composite index | Create and deploy the corresponding index |
| Firestore repository query fails to run | Unsupported filter or OR used | Switch to native Firestore query builder |
| @Query does not work on Native | Firestore Native has no GQL | Use query methods/template/client |
| Subcollection retains data after delete | Deleting parent does not cascade | Implement recursive/background cleanup |
| Transaction conflict | Multiple requests modifying the same document | Use optimistic locking or bounded retries |
| Datastore entity not found | Wrong kind, ID type, or namespace | Cross-check @Entity, @Id, database, and namespace |
| Datastore query missing index | Composite index not yet created | Check GQL/query pattern and deploy index |
| deleteBy... error inside transaction | Query-delete executes outside transaction | Use appropriate key/ancestor operations or split transactions |
| @Transactional runs on wrong database | Multiple transaction managers in context | Explicitly specify the right manager |
| Passes locally but fails on cloud | Emulator does not verify IAM/runtime network | Test on sandbox with workload identity |

## 16. Practical Exercises

### Exercise A — Firestore Reactive CRUD

Create OrderDocument and OrderDocumentRepository. Write APIs to create, read, update, and delete orders using Mono/Flux. Verify the controller never calls block().

### Exercise B — Query Methods and Indexes

Write a method finding orders by customer, status, and createdAt. Create the required composite index. Test a query missing an index and inspect the error to learn how to resolve it.

### Exercise C — FirestoreTemplate and Subcollections

Use FirestoreReactiveOperations.withParent to store OrderItem inside a subcollection. Write a cleanup job deleting children before deleting the parent and ensure the job is resumable.

### Exercise D — Firestore Transactions

Use ReactiveFirestoreTransactionManager and TransactionalOperator to update an order and insert an audit document in one transaction. Ensure all reads occur before writes.

### Exercise E — Datastore Repositories

Create DatastoreOrder and DatastoreOrderRepository. Implement CRUD, derived query methods by customer/status, count, exists, and Slice pagination.

### Exercise F — GQL and Projections

Write a custom @Query with named parameters, query `__key__`, and create an interface projection. Create composite indexes if required by the queries.

### Exercise G — DatastoreTemplate Transactions

Write performTransaction to read an order, validate status, and update it. Compare with @Transactional(transactionManager = "datastoreTransactionManager").

### Exercise H — Emulators and Security

Run two test suites with the Firestore Emulator and Datastore Emulator. Deploy an integration test to a real sandbox using a minimal service account; verify IAM and query/index behavior.

### Self-Check Questions

1. Why do Firestore Native and Datastore mode require two separate repository abstractions?
2. Which repository type does FirestoreReactiveRepository extend?
3. When should a method return Mono vs. Flux?
4. Why must block() not be called on a WebFlux request path?
5. What data type does @DocumentId require?
6. How does @PropertyName help handle naming mismatches?
7. Which filters do Firestore query methods support and how are they combined?
8. Why is GQL custom @Query not usable for Native mode?
9. When should you use FirestoreTemplate instead of a repository?
10. What is withParent used for?
11. Does deleting a parent document automatically delete subcollections?
12. Which operator pairs with ReactiveFirestoreTransactionManager?
13. Why must transactions perform reads before writes?
14. How does @UpdateTime(version = true) protect concurrent updates?
15. What is the second generic parameter of DatastoreRepository<T, ID> used for?
16. Which filters do Datastore query methods support?
17. Why does Page cost more queries than Slice?
18. Why can't derived deleteBy... methods be used inside a Datastore transaction?
19. When should you use custom GQL and DatastoreTemplate?
20. How do you distinguish IAM errors, index errors, and reactive pipeline errors?

**Expected outcome:** learners can implement reactive Firestore repositories for Native mode and Datastore repositories for Datastore mode, write queries within API limits, use templates/clients for advanced cases, manage transactions and indexes appropriately, keep reactive pipelines non-blocking, and test integrations with emulators and runtime identities.

## References

- [Spring Framework on Google Cloud 8.2.1 — Spring Data Cloud Firestore](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/index.html#spring-data-cloud-firestore)
- [Spring Framework on Google Cloud 8.2.1 — Spring Data Cloud Datastore](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/datastore.html)
- [Firestore query and data model](https://docs.cloud.google.com/firestore/native/docs/query-data/queries)
- [Firestore transactions](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions)
- [Datastore queries](https://docs.cloud.google.com/datastore/docs/concepts/queries)
- [Datastore transactions](https://docs.cloud.google.com/datastore/docs/concepts/transactions)
- [Firestore Emulator](https://firebase.google.com/docs/emulator-suite/connect_firestore)
