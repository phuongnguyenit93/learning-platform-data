# Distinguishing Datastore and Firestore When Choosing a Storage Model

## Learning Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot integrates managed services from AWS, Azure, and Google Cloud to access data, storage, messaging, and manage identity/permissions. On Google Cloud, Datastore and Firestore are often mentioned together because Firestore is the next generation of Cloud Datastore and still provides a Datastore API compatibility mode.

This lesson helps you properly distinguish between **Firestore in Datastore mode** and **Firestore in Native mode**, and then select the right Spring integration:

1. Understand the naming of Cloud Datastore, Firestore, and the two current database modes.
2. Compare data models: kind/entity/key vs. collection/document/field.
3. Choose how to model parent-child relationships, embedded data, and references.
4. Evaluate queries, indexes, transactions, consistency, and realtime capabilities.
5. Choose Spring Data Cloud Datastore or Spring Data Cloud Firestore.
6. Configure starters, ADC, IAM, and emulators in Spring Boot.
7. Design schema evolution, testing, and data migration plans.
8. Recognize when NoSQL is appropriate and when to choose Cloud SQL or Spanner.

> **Scope:** Examples use Java and Spring Boot. Spring Framework on Google Cloud, Spring Boot, and Java versions must be compatible according to your project's BOM. Property names, repository APIs, and features may vary across major versions; verify against the reference documentation for the exact BOM in use. Per the Spring Framework on Google Cloud 8.2.1 compatibility matrix, the 8.x branch is compatible with Spring Boot 4.0/4.1, 7.x with Boot 3.5, and 6.x with Boot 3.4.

## 1. Cloud Datastore and Firestore: Understanding the Naming

### 1.1. Datastore Is No Longer a Separate Database Product

Cloud Datastore is the historical name of a managed NoSQL document/entity database service. Firestore succeeds Datastore and provides a compatibility API so existing Datastore applications continue to run. Therefore, when someone says "Datastore" in modern Google Cloud architecture, you usually need to clarify whether they mean:

- **Firestore in Datastore mode:** a database using the Datastore API, compatible with the kind/entity/key model and legacy Cloud Datastore applications.
- **Firestore in Native mode:** a database using the Firestore API and collection/document model, supporting Firestore features for backend, web, and mobile applications.

Firestore is the current service name; Datastore mode is a compatibility API/access mode. The two names do not represent two completely separate database engines.

### 1.2. Database Mode Is a Database-Level Choice

When creating a Firestore database, choose the data access mode matching the edition. Standard edition supports Native mode or Datastore mode; Enterprise edition supports Native mode or MongoDB compatibility mode. A database has one mode at a time; applications must use the corresponding API and client library. Mode changes are only allowed when the database is empty per database management rules. With live data, changing modes cannot be treated like changing a property in application.yml.

A Google Cloud project can manage multiple databases, so do not assume every database in a project uses the same mode. Verify the database ID and mode of the exact resource the application will connect to.

### 1.3. Quick Comparison

| Criterion | Firestore in Datastore mode | Firestore in Native mode |
| --- | --- | --- |
| Primary API | Datastore API | Firestore API |
| Data model | Kind, entity, property, key | Collection, document, field |
| Identity | Entity key; has namespace, kind, ID, and ancestor path | Document path and document ID |
| Query | GQL/Datastore query | Firestore query API |
| Hierarchical relationships | Ancestor/descendant via key path | Subcollections and document references |
| Indexes | Built-in indexes and composite indexes via Datastore config | Single-field and composite indexes per Firestore |
| Realtime listeners for web/mobile | Lacks Native API realtime features | Supports realtime listeners and corresponding client SDKs |
| Offline cache on mobile/web SDKs | No equivalent Datastore SDK suite | Offline persistence on supported client SDKs |
| Spring Data | Spring Data Cloud Datastore | Spring Data Cloud Firestore with reactive repositories |
| Legacy Datastore app compatibility | Yes | Does not use Datastore API directly |

Both modes are managed NoSQL document databases supporting transactions and strong consistency. Key differences lie in APIs, data models, query features, client ecosystems, and how applications are structured. [Google Cloud describes both modes and compatibility limits here](https://docs.cloud.google.com/datastore/docs/firestore-or-datastore).

### 1.4. Diagram of the Two Spring Integration Paths

~~~mermaid
flowchart TD
    APP["Spring Boot application"] --> CHOICE{"Database mode?"}
    CHOICE -->|"Datastore mode"| DS["Spring Data Cloud Datastore"]
    CHOICE -->|"Native mode"| FS["Spring Data Cloud Firestore"]
    DS --> DAPI["Datastore API / GQL"]
    FS --> FAPI["Firestore API / query builder"]
    DAPI --> DB["Firestore database"]
    FAPI --> DB
    ADC["ADC + workload service account"] --> DAPI
    ADC --> FAPI
~~~

The two starters have separate repository abstractions. Do not use DatastoreRepository to access Native mode, and do not use FirestoreReactiveRepository to access Datastore mode.

## 2. Datastore Mode Data Model

### 2.1. Kind, Entity, and Property

Datastore mode organizes data into entities. Each entity belongs to a **kind** and contains **properties**:

| Concept | Example | Role |
| --- | --- | --- |
| Kind | Order | Categorizes entities |
| Entity | An order with a specific ID | Unit of data |
| Property | customerId, status, createdAt | Attribute of an entity |
| Key | Order / 10001 | Unique identifier |
| Namespace | tenant-a | Logical data namespace partition |
| Ancestor path | Customer/42/Order/10001 | Hierarchical relationship in the key |

Entities of the same kind are not required to have the same set of properties or the same data type for a property. This is a schemaless model. Even so, applications should proactively standardize fields and types so queries, validation, and mapping stay predictable.

For example, two entities of kind Order can have different fields:

~~~json
{
  "customerId": "customer-42",
  "status": "PAID",
  "total": 125000
}
~~~

~~~json
{
  "customerId": "customer-77",
  "status": "PENDING",
  "currency": "VND"
}
~~~

This flexibility enables adding fields without DDL migrations like in a relational database. In return, the application must control schema contracts, null/missing fields, data types, and backward compatibility.

### 2.2. Entity Key

A Datastore mode key consists of kind, identifier, and optionally an ancestor path. The identifier can be:

- An application-assigned string, e.g., order-2026-001.
- A numeric ID automatically generated by Datastore.

Namespaces allow separating data by namespace within the same database. Namespaces are useful for multitenancy or logical partitioning, but they are **not a security boundary**. If a tenant must not access another tenant's data, the application must still verify tenant identity and restrict IAM permissions appropriately.

Example key with an ancestor:

~~~text
Customer("customer-42")
  └── Order(10001)
       └── OrderItem("item-1")
~~~

The child key contains the ancestor path. This makes it possible to identify entities belonging to the same data tree and run ancestor queries.

### 2.3. Relationships in Datastore Mode

Spring Data Cloud Datastore supports several ways to represent relationships:

- **Embedded entity:** child object stored directly inside a property of the parent entity.
- **@Descendants:** child entity exists independently in its own kind, but its key includes the ancestor path.
- **@Reference:** stores a key referencing an independent entity in another kind.
- **@LazyReference:** similar to reference, but defers loading the referenced entity until the property is accessed.

Choose embedded when the object is small, always read with the parent, and needs no independent identity. Choose descendants when the child shares the parent's lifecycle and needs ancestor queries. Choose reference when the two entities have independent lifecycles.

With @Descendants, the child entity has its own kind and its ID property uses the Key type to hold the ancestor path; Spring Data can read/save descendants along with the parent. With @Reference, the property stores the key of an entity of another kind and Spring Data converts the key into the corresponding Java object. References are resolved on entity read/write; use @LazyReference if you want to defer loading the referenced entity. Descendant/reference collections are not guaranteed to preserve their original order after reading.

### 2.4. No Relational-Style Schema DDL

Datastore mode does not create tables via CREATE TABLE. Kinds and properties are formed when the application writes entities. You still need to document your business schema and manage migrations via code/configuration, but there is no rigid DDL like PostgreSQL.

In particular, entity IDs/keys are not columns you can arbitrarily rename/change. A key is the identity of an entity; changing a key essentially means creating a new entity and handling the old one.

## 3. Firestore Native Mode Data Model

### 3.1. Collection, Document, and Field

Firestore Native mode organizes data as a collection/document tree:

| Concept | Example | Role |
| --- | --- | --- |
| Collection | orders | Group of documents |
| Document | orders/order-10001 | Unit of data |
| Field | status, customerId, total | Data inside a document |
| Subcollection | orders/order-10001/items | Child collection of a document |
| Document reference | Reference to customers/customer-42 | Link to another document |

A document contains key-value pairs. Fields can be strings, numbers, booleans, timestamps, geopoints, arrays, maps, or references. Documents can contain nested objects, though you must consider size limits and update frequency.

Document example:

~~~json
{
  "customerId": "customer-42",
  "status": "PAID",
  "total": 125000,
  "createdAt": "2026-11-24T09:30:00Z",
  "shippingAddress": {
    "city": "Ho Chi Minh City",
    "country": "VN"
  },
  "tags": ["priority", "online"]
}
~~~

Documents within the same collection can have different fields. In production applications, keep field contracts relatively consistent so queries and mapping do not break on arbitrary types.

### 3.2. Subcollections and Document References

If an order's item count grows over time, do not stuff every item into a large array in the parent document. You can use a subcollection:

~~~text
orders/
  order-10001/
    status: "PAID"
    customerId: "customer-42"
    items/
      item-1/
      item-2/
  order-10002/
    status: "PENDING"
    customerId: "customer-77"
    items/
      item-1/
~~~

Subcollections fit growing lists, independent queries, or collection group queries. Document references fit linking independent documents such as orders and customers.

Note: deleting a parent document does not automatically delete subcollections underneath it. If business logic requires cascade deletion, implement a controlled recursive delete or background cleanup job.

### 3.3. Embedded Data vs. Subcollection?

| Criterion | Embedded map/array | Subcollection |
| --- | --- | --- |
| Element count | Small, bounded, and rarely changes | Can grow over time |
| Reading data | Read together with parent | Can be queried separately |
| Updating | May rewrite the parent document | Writes individual child documents |
| Querying | Queries fields inside the document | Queries collection or collection group |
| Deleting parent | Embedded fields vanish with document | Subcollection remains unless deleted separately |

For example, a shipping address with a fixed structure can be embedded in the order document. A status history list or order line items can live in a subcollection if independent querying is needed.

### 3.4. Document Size Limits

Firestore Native mode imposes limits on document size and field/path counts. Do not design a document as an unbounded table holding infinite rows. For Standard edition, the published document limit is typically 1 MiB; check quotas/limits for your edition and deployment time.

## 4. Queries and Indexes: Key Differences

### 4.1. Datastore Mode Uses GQL and Indexes

Datastore mode provides GQL, a SQL-like query language. Example:

~~~sql
SELECT * FROM orders
WHERE customer_id = @customerId
  AND status = @status
ORDER BY createdAt DESC
~~~

GQL provides familiar syntax, but it is not full SQL. Datastore mode has no JOINs like a relational database. The query engine relies on indexes; built-in indexes support many simple queries, while complex queries require composite indexes.

Key points to remember:

- Datastore API/GQL now supports composite AND and OR filters; however, Spring Data Cloud Datastore derived query methods support a narrower set of filters and combine filters with AND.
- Comparisons and sorting are constrained by query/index rules.
- No joins or subqueries as in relational SQL.
- Queries require matching indexes; missing indexes cause queries to fail and return index creation suggestions.
- Properties can be excluded from indexing if you do not need to query on them.

### 4.2. Composite Indexes and index.yaml

When queries filter on multiple properties or require multiple sort orders, Datastore mode may need a composite index. Indexes are declared in index.yaml configuration and deployed alongside the application/pipeline.

Illustrative example:

~~~yaml
indexes:
  - kind: orders
    properties:
      - name: customer_id
      - name: status
      - name: createdAt
        direction: desc
~~~

This is an illustrative structure; exact syntax must match your index deployment tool and actual query definitions. Do not copy this index into production if no query pattern uses it.

### 4.3. Native Mode Query API

Firestore Native mode uses the Firestore API query builder, not GQL. Queries target a collection or collection group. Capabilities include equality, range filters, array filters, in, not-in, and logical OR within supported conditions.

Java client example:

~~~java
CollectionReference orders = firestore.collection("orders");

ApiFuture<QuerySnapshot> future = orders
        .whereEqualTo("customerId", "customer-42")
        .whereEqualTo("status", "PAID")
        .orderBy("createdAt", Query.Direction.DESCENDING)
        .limit(20)
        .get();

QuerySnapshot snapshot = future.get();
for (QueryDocumentSnapshot document : snapshot.getDocuments()) {
    System.out.println(document.getId() + " " + document.getString("status"));
}
~~~

Firestore Native mode does not support SQL JOINs. If data from multiple collections is needed, applications typically use document references, denormalization, or multiple separate queries. Collection group queries let you query subcollections sharing the same collection ID across multiple levels in the document tree.

### 4.4. Indexes in Native Mode

Firestore automatically creates certain single-field indexes and requires composite indexes for some queries. When a query needs a missing composite index, the returned error typically includes a link to create the index.

Do not mechanically create indexes for every field. Indexes speed up queries but increase storage costs and write amplification. Fields that never need querying can be exempted from indexing as needed.

### 4.5. Spring Repository Query Limits by Mode

This is an important distinction when migrating code:

- Spring Data Cloud Datastore supports derived query methods and custom GQL via @Query.
- Spring Data Cloud Firestore provides reactive query methods by method name; GQL @Query is not used for Native mode because Firestore has no GQL.
- Query methods in both integrations only support the subset of operators corresponding to their database API. Do not assume every Spring Data JPA predicate works.

For complex queries or specialized features, use DatastoreTemplate/FirestoreOperations or the native client API.

## 5. Consistency and Transactions

### 5.1. Strong Consistency in Both Modes

Firestore in Datastore mode now provides strong consistency for key lookups and queries. Do not copy claims from very old Cloud Datastore documentation stating that all non-ancestor queries are eventually consistent.

Firestore Native mode also provides strong consistency for reads and queries per Firestore semantics. Therefore, choosing Native vs. Datastore mode should not be based on an assumption that one mode has strong consistency while the other is only eventual.

### 5.2. Transactions in Datastore Mode

Datastore mode supports read-write transactions and read-only transactions. A transaction is atomic: all operations commit together or none are applied.

Transactions can encounter contention when multiple requests modify the same entity or related data regions. The database has concurrency modes:

- **Pessimistic:** transactions use locks to guarantee isolation.
- **Optimistic:** transactions can execute concurrently; conflicts are detected at commit time.
- **Optimistic with entity groups:** legacy compatibility mode with entity group constraints.

Do not design new applications around legacy Datastore entity group constraints unless a specific compatibility requirement exists. Check the concurrency mode of existing databases and test workloads before changing it.

### 5.3. Transactions in Native Mode

Firestore Native mode supports:
- **Read-write transactions:** read data and then write multiple documents atomically.
- **Batched writes:** group multiple write operations that require no prior read into one atomic commit.

Inside a transaction, perform all reads before writes. If read data changes concurrently, Firestore may re-run the transaction callback. Therefore, callbacks must be safe to execute multiple times.

### 5.4. Retries and Idempotency

Even if the database returns an error at commit time, the application cannot always be sure whether the request was applied. For business operations like creating orders, deducting funds, or confirming payments:

1. Use an idempotency key or unique business key.
2. Keep transactions short.
3. Do not send emails, call payment gateways, or publish messages directly inside the transaction callback.
4. Write event/outbox records in the same transaction when events need to be emitted.
5. Use a separate worker to dispatch events and handle duplicates safely.

Do not retry every exception infinitely. Classify transient, conflict, permission, and validation errors before deciding whether to retry.

## 6. Choosing the Right Spring Integration

### 6.1. Spring Data Cloud Datastore for Datastore Mode

Spring Framework on Google Cloud provides the starter:

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

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-data-datastore</artifactId>
    </dependency>
</dependencies>
~~~

spring-cloud-gcp.version is a project-selected property per the compatibility matrix. The BOM manages compatible versions of Spring Cloud GCP modules; avoid pinning individual starter versions separately.

The starter auto-configures DatastoreTemplate, the Datastore client, and repositories discovered in packages. Spring Data Cloud Datastore is compatible with Firestore in Datastore mode, not Native mode.

### 6.2. Configuring Datastore Mode

~~~yaml
spring:
  cloud:
    gcp:
      project-id: rental-platform-dev
      datastore:
        project-id: rental-platform-dev
        database-id: "(default)"
        namespace: orders
~~~

Common properties:

| Property | Meaning |
| --- | --- |
| spring.cloud.gcp.datastore.enabled | Enables/disables Datastore client autoconfiguration |
| spring.cloud.gcp.datastore.project-id | Project containing the Datastore database |
| spring.cloud.gcp.datastore.database-id | Database ID; typically defaults to (default) |
| spring.cloud.gcp.datastore.namespace | Default namespace |
| spring.cloud.gcp.datastore.host | Host/port of the service or emulator |
| spring.cloud.gcp.datastore.emulator.enabled | Enables Datastore Emulator autoconfiguration |
| spring.cloud.gcp.datastore.emulator.port | Emulator port when auto-started by the starter |

If using a database ID other than (default), ensure both the property and IAM/database resources point to the exact same database.

### 6.3. Mapping Datastore Mode POJOs

Order entity example:

~~~java
import com.google.cloud.spring.data.datastore.core.mapping.Entity;
import com.google.cloud.spring.data.datastore.core.mapping.Field;
import com.google.cloud.Timestamp;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;

@Entity(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    @Field(name = "customer_id")
    private String customerId;

    private String status;

    private Long totalAmount;

    private Timestamp createdAt;

    @Transient
    private String displayLabel;

    public OrderEntity() {
    }

    // Getters and setters omitted for brevity.
}
~~~

Meanings:

- @Entity specifies the kind.
- @Id marks the entity ID/key.
- @Field maps a Java property to a property name in Datastore.
- @Transient marks a field not persisted to the database.

If the ID is Long and its value is null, Datastore can automatically assign a numeric ID. Do not use primitive long if you need to distinguish an unassigned ID state from ID 0.

### 6.4. Datastore Mode Repositories

~~~java
import com.google.cloud.spring.data.datastore.repository.DatastoreRepository;
import java.util.List;
import java.util.Optional;

public interface OrderRepository
        extends DatastoreRepository<OrderEntity, Long> {

    List<OrderEntity> findByCustomerId(String customerId);

    List<OrderEntity> findByCustomerIdAndStatus(
            String customerId, String status);

    Optional<OrderEntity> findFirstByCustomerIdAndStatus(
            String customerId, String status);
}
~~~

Spring Data generates the repository implementation. Datastore mode's filter set is more restricted than JPA: query methods do not support all operators, JOINs, or arbitrary SQL expressions. Check the reference for your library version.

Per the current reference, Spring Data Cloud Datastore query methods combine filters using AND and support equality, not-equal, greater/greater-or-equal, less/less-or-equal, and is-null. GQL/Datastore API has additional query capabilities, including composite AND/OR; do not equate repository method limits with the entire Datastore API.

### 6.5. Custom GQL with @Query

~~~java
import com.google.cloud.spring.data.datastore.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface OrderGqlRepository
        extends DatastoreRepository<OrderEntity, Long> {

    @Query("SELECT * FROM orders WHERE customer_id = @customer")
    List<OrderEntity> findOrdersByCustomer(
            @Param("customer") String customerId);
}
~~~

The GQL placeholder name after `@` must match the `@Param` name. Always bind parameters; never concatenate user data strings into GQL.

### 6.6. DatastoreTemplate and Save Semantics

DatastoreTemplate fits when you need direct operations with keys, queries, transactions, or features not cleanly expressed via repositories.

~~~java
import com.google.cloud.spring.data.datastore.core.DatastoreTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderWriteService {

    private final DatastoreTemplate datastoreTemplate;

    public OrderWriteService(DatastoreTemplate datastoreTemplate) {
        this.datastoreTemplate = datastoreTemplate;
    }

    public OrderEntity save(OrderEntity order) {
        return datastoreTemplate.save(order);
    }
}
~~~

save has update-or-insert (upsert) semantics. insert fails if the entity already exists. When you need to ensure an entity does not yet exist, use insert or an appropriate business key/transaction rather than assuming save is a pure INSERT.

### 6.7. Transactions with DatastoreTransactionManager

The Datastore starter provides DatastoreTransactionManager; repositories and templates can participate in @Transactional:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;

    public OrderApplicationService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "datastoreTransactionManager")
    public void markPaid(Long orderId) {
        OrderEntity order = orderRepository.findById(orderId)
                .orElseThrow();
        order.setStatus("PAID");
        orderRepository.save(order);
    }
}
~~~

Do not call performTransaction nested inside a method already annotated with @Transactional on the same Datastore transaction. Spring Data Cloud Datastore does not support arbitrary nested transactions.

## 7. Spring Data Cloud Firestore for Native Mode

### 7.1. Firestore Native Starter

Spring Framework on Google Cloud provides a starter for Firestore Native mode:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-data-firestore</artifactId>
</dependency>
~~~

This module provides Spring Data Reactive Repositories, FirestoreTemplate, and the Firestore client. This is a separate integration from Datastore mode.

If you only want to use the Firestore Java client without Spring Data repositories, you can use spring-cloud-gcp-starter-firestore; this starter auto-configures the Firestore bean.

### 7.2. Configuring Firestore Native

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

Common properties:

| Property | Meaning |
| --- | --- |
| spring.cloud.gcp.firestore.enabled | Enables/disables Firestore autoconfiguration |
| spring.cloud.gcp.firestore.project-id | Project containing the Firestore database |
| spring.cloud.gcp.firestore.database-id | Database ID; typically (default) |
| spring.cloud.gcp.firestore.emulator.enabled | Connects to the emulator |
| spring.cloud.gcp.firestore.host-port | Host/port of the Firestore service or emulator |
| spring.cloud.gcp.firestore.credentials.location | Custom credentials if not using default ADC |

Use ADC in local development and workload identity/service accounts attached to Cloud Run, GKE, or Compute Engine in production. Do not package service account JSON keys in images or Git.

### 7.3. Mapping Firestore Native POJOs

~~~java
import com.google.cloud.firestore.annotation.DocumentId;
import com.google.cloud.firestore.annotation.PropertyName;
import com.google.cloud.spring.data.firestore.Document;
import com.google.cloud.Timestamp;

import java.util.List;

@Document(collectionName = "orders")
public class OrderDocument {

    @DocumentId
    private String id;

    private String customerId;

    private String status;

    private Long totalAmount;

    private Timestamp createdAt;

    private List<String> tags;

    public OrderDocument() {
    }

    @PropertyName("customer_id")
    public String getCustomerId() {
        return customerId;
    }

    @PropertyName("customer_id")
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    // Getters and setters omitted for brevity.
}
~~~

- @Document specifies the collection.
- @DocumentId marks the document ID; when the ID is null, Firestore can generate an ID on save.
- @PropertyName maps the persisted field name.
- Lists/maps and nested objects can be stored as embedded arrays/maps inside the document.

Do not confuse Firestore's @DocumentId with Datastore's @Id. These are two separate mapping models.

### 7.4. Reactive Repositories

Firestore Spring Data provides FirestoreReactiveRepository:

~~~java
import com.google.cloud.spring.data.firestore.FirestoreReactiveRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface OrderDocumentRepository
        extends FirestoreReactiveRepository<OrderDocument> {

    Flux<OrderDocument> findByCustomerIdAndStatus(
            String customerId, String status);

    Flux<OrderDocument> findByStatusOrderByCreatedAtDesc(String status);

    Mono<OrderDocument> findFirstByCustomerId(String customerId);
}
~~~

Repositories use Reactor Mono and Flux. Do not call block() on a WebFlux request path if you want to preserve a non-blocking flow. If the application is synchronous Spring MVC, consider using the Firestore Java client/FirestoreTemplate or bridging intentionally at the boundary.

### 7.5. FirestoreOperations and FirestoreTemplate

FirestoreOperations and FirestoreTemplate provide reactive APIs for save, read, query, delete, transactions, and subcollections. Use the template when derived query methods are insufficiently expressive or when accessing specific Firestore features.

Native Firestore does not use GQL. Spring Data Cloud Firestore does not support GQL-style custom @Query; use the query builder or native Firestore client API.

Reactive repository query methods support a set of operators mapped by Spring Data to Firestore—such as equality, not-equal, range, null, contains, in, and not-in within API limits. Filters in derived method names are combined with AND. If you need OR expressions or query capabilities not expressed by repositories, use the Firestore query builder/native client. Do not assume every method name valid in Spring Data JPA works in Firestore.

In the current reference, Spring Data Cloud Firestore does not yet support query by example, projections, or auditing. If a use case requires these features, use the native client/template or implement mapping/auditing at the application layer.

### 7.6. Transactions and Optimistic Locking

Spring Data Cloud Firestore supports transactions via @Transactional and the starter's ReactiveFirestoreTransactionManager. If the application has multiple transaction managers, specify the exact manager for the reactive transaction boundary. Firestore transactions can be re-executed on conflict; callbacks must avoid external side effects outside the database. Reads inside a transaction must happen before writes.

Firestore also provides update timestamps and optimistic locking. You can use an @UpdateTime(version = true) field to verify the document has not changed since it was last read. This is useful when multiple requests update the same document concurrently.

## 8. IAM, Security Rules, and Workload Identity

### 8.1. Datastore Mode: IAM for Server Workloads

Server-side Spring Boot applications use ADC to authenticate with Google Cloud. Common roles:

- roles/datastore.user: read/write data permissions for workloads.
- roles/datastore.viewer: read-only data permissions.
- roles/datastore.owner: broad administrative permissions; should not be granted to runtime APIs unnecessarily.

Separate runtime service accounts from migration/index administration principals. Do not grant Owner just so an application can run CRUD.

### 8.2. Native Mode: Server SDK and Mobile/Web SDK Have Different Security Models

Firestore Native has two common access patterns:

- **Mobile/web client SDKs:** requests are evaluated by Firebase Authentication and Firestore Security Rules.
- **Server client SDKs in Spring Boot:** requests use ADC and IAM. Server client libraries bypass Firestore Security Rules.

This is crucial: writing Security Rules does not protect requests sent by the Spring Boot server SDK. The backend must have proper IAM and enforce business authorization itself based on the authenticated user/tenant.

### 8.3. IAM Does Not Replace Business Authorization

A service account permitted to read data in the database does not mean every API caller is allowed to view every document. The backend must verify:

- User identity from the access token/session.
- Tenant/customer ID belonging to the user.
- View/edit permissions per business rules.
- Which fields are allowed to be returned.
- Never trust a tenant ID sent by the client without verification.

Namespaces in Datastore mode and document paths in Firestore Native are merely ways to organize data; they do not automatically establish security boundaries.

### 8.4. Data Protection and Logging

- Never log access tokens, service account keys, or full personal data.
- Grant only minimal roles to each service.
- Enable audit logging and monitoring per organizational requirements.
- Define retention, backup/export, and deletion policies.
- Test IAM with the actual runtime service account, not only a local developer account.

## 9. Indexes, Schema Evolution, and Performance

### 9.1. Datastore Mode

Every Datastore mode query relies on indexes. You should:

1. Document repository query patterns.
2. Create required composite indexes.
3. Deploy index.yaml through a pipeline.
4. Mark properties that do not need querying as unindexed when appropriate.
5. Monitor query latency and index build status.

Do not treat schemaless entities as an excuse to skip schema contracts. Version fields and migration logic inside the application.

### 9.2. Firestore Native Mode

Firestore automatically creates single-field indexes and requires composite indexes for certain queries. Manage indexes through configuration/console or deployment tools. Inspect the index creation link from query errors in dev, review the definition, and then promote it to production.

Do not embed unbounded growing lists in a single document. Use subcollections when child data grows independently; remember that deleting a parent does not cascade-delete subcollections.

### 9.3. Denormalization and Multi-Document Updates

Because both modes are NoSQL, data often needs to be denormalized for read patterns. For instance, an order can store customerName at purchase time for fast rendering without joining a customer document.

In return, if the customer's name changes, denormalized copies do not sync automatically. Decide whether to:
- Accept a snapshot of the name at order placement time.
- Fan out updates via events/background jobs.
- Read customer data separately when the latest name is required.

Choose storage patterns based on consistency requirements; never duplicate data without a synchronization strategy.

## 10. Emulators and Integration Testing

### 10.1. Datastore Emulator

Spring Data Cloud Datastore can auto-start the Datastore Emulator:

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

The emulator is suitable for testing mapping, repositories, GQL, CRUD, and basic transactions. You can connect to a self-managed emulator host/port if autoconfiguration is not enabled.

### 10.2. Firestore Emulator

Firestore Native uses the Firebase Emulator Suite/Firestore Emulator. Example:

~~~yaml
spring:
  cloud:
    gcp:
      firestore:
        emulator:
          enabled: true
        host-port: localhost:8080
~~~

The port above is an example; check the actual port of the emulator in your test environment. The Firestore starter can connect to the emulator when the corresponding host-port is configured.

### 10.3. Recommended Tests

| Test group | Datastore mode | Firestore Native |
| --- | --- | --- |
| Mapping | @Entity, @Id, @Field, @Descendants | @Document, @DocumentId, @PropertyName |
| CRUD | DatastoreRepository/Template | FirestoreReactiveRepository/Template |
| Query | Query methods and GQL @Query | Query methods and Firestore query builder |
| Index | Built-in and composite index.yaml | Single-field/composite indexes |
| Relationship | Embedded, ancestor, reference | Embedded, subcollection, document reference |
| Transaction | DatastoreTransactionManager | Firestore transaction support |
| Security | IAM service account | IAM for server SDK; Security Rules for mobile/web |
| Integration | Datastore Emulator and real sandbox | Firestore Emulator and real sandbox |

Emulators do not fully replace testing on a sandbox project. Verify IAM, index provisioning, quotas, concurrency, and network behavior with the actual runtime identity.

## 11. Migration Between Datastore Mode and Firestore Native

### 11.1. You Cannot Just Swap Starters

The two modes have different APIs, data models, query languages, key/document IDs, and Spring mappings. Switching from DatastoreRepository to FirestoreReactiveRepository requires redesigning:

- Entity keys and document IDs.
- Ancestor paths/descendant relationships and subcollections/document references.
- GQL queries and Firestore query builder calls.
- index.yaml and Firestore composite indexes.
- Transaction boundaries and concurrency assumptions.
- Namespaces and tenant isolation.
- Synchronous Spring repositories and reactive repositories.

### 11.2. Checking Mode Changes and Existing Data

Database mode is a database-level property. Management APIs only allow changing the database type when the database is empty. If the database already contains data, create a target database with the desired mode and plan an export/transform/import or dedicated migration pipeline.

Do not delete old databases or change modes in production just to experiment. Before migrating, audit data, indexes, key formats, references, query behavior, and downtime/cutover requirements.

### 11.3. Recommended Migration Steps

1. Inventory existing kinds/entities, properties, namespaces, keys, and ancestor paths.
2. List all GQL queries, indexes, and transactions.
3. Design target collections/documents/subcollections and document IDs.
4. Build repeatable mapping and transformation logic.
5. Create a sandbox Native mode database and required indexes.
6. Run trial export/import, reconciling counts and checksums/business invariants.
7. Run controlled shadow reads or dual-writes if minimal downtime is required.
8. Test IAM, client-side Security Rules, and server-side business authorization.
9. Shift traffic according to plan, monitor errors/latency, and retain a rollback plan.
10. Decommission the old database only after reconciliation and cutover approval.

If an application uses the Datastore API due to App Engine or legacy code dependencies, staying on Datastore mode can be a sensible choice. There is no need to migrate solely because the newer product name is Firestore.

## 12. Choosing a Database by Requirements

| Need | Suitable choice |
| --- | --- |
| Existing App Engine/Datastore API application | Firestore in Datastore mode |
| Spring Boot backend already using kind/entity/key/GQL | Datastore mode + Spring Data Cloud Datastore |
| Mobile/web app needing realtime listeners and offline cache | Firestore Native mode |
| New Spring Boot backend needing document model and reactive repositories | Firestore Native + Spring Data Cloud Firestore |
| Queries needing JOINs, foreign keys, complex relational SQL | Cloud SQL |
| Large-scale distributed relational workload, multi-region transactions | Cloud Spanner |
| Document data with loose relationships and suitable queries/indexes | Firestore Native or Datastore mode per required API/features |

Firestore is a document database, not a drop-in relational database replacement for every workload. If a use case requires joins, complex relational constraints, SQL reporting, or multi-table transactions, evaluate Cloud SQL/Spanner.

## 13. Common Errors and How to Handle Them

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| PERMISSION_DENIED | ADC wrong principal or missing IAM role | Check runtime service account and roles/datastore.user / appropriate Firestore role |
| Spring repository not created | Missing starter or wrong package scan | Check dependencies, packages, and repository interfaces |
| Datastore mode reports kind not found | Wrong @Entity(name=...) or database ID | Cross-check kind, project, and database |
| Firestore reports document not found | Wrong collection/document path or database ID | Check @Document, @DocumentId, and configuration |
| Datastore query fails to run | Missing composite index or unsupported filter | Check GQL, index.yaml, and deployed indexes |
| Firestore query demands index | Missing composite index | Create the suggested index, review, and deploy |
| Native Firestore lacks GQL | Using Datastore @Query for Native mode | Use query methods or Firestore query builder |
| Deleting parent leaves children behind | Subcollections do not cascade delete | Write recursive delete or background cleanup |
| Transaction conflict | Multiple requests modifying the same entity/document | Shorten transactions, bounded retries, and idempotency |
| Runs locally but fails on Cloud Run | Emulator does not use real IAM/networking | Test on sandbox with workload identity |
| Mode change fails | Database already contains data | Create target database and migrate data |
| Backend assumes Security Rules protect it | Server client SDK bypasses Security Rules | Configure IAM and business authorization in backend |

## 14. Practical Exercises

### Exercise A — Identify Mode

Create a sandbox Firestore database. Record the database type, database ID, and location. Verify which API/client library is used for the chosen mode.

### Exercise B — Spring Data Datastore

Add spring-cloud-gcp-starter-data-datastore. Create OrderEntity with @Entity, @Id, @Field. Build a repository finding orders by customer and status; add a parameterized GQL @Query.

### Exercise C — Spring Data Firestore Native

Create a Native mode database. Add spring-cloud-gcp-starter-data-firestore, mapping OrderDocument with @Document and @DocumentId. Write a reactive repository returning Flux<OrderDocument> and test querying by status.

### Exercise D — Compare Relationships

Model Order and OrderItem in three ways: embedded, Datastore ancestor/descendant, and Firestore subcollection. Measure read counts, parent deletion behavior, and independent child queryability.

### Exercise E — Indexes and Queries

Create a query filtering by customer and status and sorting by timestamp. Identify the composite index needed in each mode. Test the missing-index error and deploy indexes through a pipeline.

### Exercise F — Transactions and Idempotency

Write an operation confirming an order and updating an audit/event inside a transaction. Simulate conflicts and retries; verify the callback does not send duplicate messages. Propose an outbox pattern when events must be published.

### Exercise G — Security

Run the backend with a dedicated service account having minimal roles. With Native mode, verify the server SDK uses IAM rather than Security Rules. Implement business authorization by customer/tenant ID.

### Exercise H — Migration Plan

Build a mapping table from Kind/Entity/Key/Namespace/Ancestor to Collection/Document/Document ID/Subcollection/Reference. Build a trial batch migration and verify counts, key mappings, field types, and query results.

### Self-Check Questions

1. How are Cloud Datastore and Firestore related?
2. On which API does Firestore in Datastore mode differ from Native mode?
3. At what level is database mode chosen?
4. What concepts in the Native model correspond to kind, entity, property, and key?
5. Is a namespace a tenant security boundary?
6. When should ancestor/descendant relationships be used in Datastore mode?
7. How does a subcollection differ from an embedded array?
8. Why doesn't deleting a parent document automatically delete subcollections?
9. How does GQL differ from the Firestore query builder?
10. Why does Datastore mode require composite indexes?
11. Is Spring Data Cloud Datastore compatible with Firestore Native?
12. What type of repository does Spring Data Cloud Firestore use?
13. Why can't GQL @Query be used for Native mode?
14. Is strong consistency a reason to choose one mode over the other?
15. Does the server Firestore client library enforce Security Rules?
16. When is roles/datastore.user needed?
17. Why must a transaction callback be idempotent?
18. Why can't you change the mode of a database containing data purely via configuration?
19. When should you choose Cloud SQL or Spanner instead of Firestore?
20. Which parts of an application must change when migrating from Datastore mode to Native mode?

**Expected outcome:** learners can accurately distinguish Firestore in Datastore mode and Native mode, choose the right Spring starter/repository, design data models and indexes around query patterns, configure IAM/ADC securely, test with emulators, and build a controlled migration plan.

## References

- [Choose between Firestore APIs](https://docs.cloud.google.com/datastore/docs/firestore-or-datastore)
- [Create and manage Firestore databases](https://docs.cloud.google.com/firestore/native/docs/manage-databases)
- [Datastore overview](https://docs.cloud.google.com/datastore/docs/concepts/overview)
- [Datastore entities, properties and keys](https://docs.cloud.google.com/datastore/docs/concepts/entities)
- [Datastore indexes](https://docs.cloud.google.com/datastore/docs/concepts/indexes)
- [Datastore transactions](https://docs.cloud.google.com/datastore/docs/concepts/transactions)
- [Datastore queries and filters](https://docs.cloud.google.com/datastore/docs/concepts/queries)
- [Firestore Native data model](https://docs.cloud.google.com/firestore/native/docs/data-model)
- [Firestore transactions and batched writes](https://docs.cloud.google.com/firestore/native/docs/manage-data/transactions)
- [Firestore IAM for server client libraries](https://docs.cloud.google.com/firestore/native/docs/security/iam)
- [Spring Data Cloud Datastore reference](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/datastore.html)
- [Spring Data Cloud Firestore reference](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.1/reference/html/index.html)
