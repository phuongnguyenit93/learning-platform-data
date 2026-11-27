# Separating Credentials, Converters, and Transaction Managers When Needed

When a **Spring Data MongoDB** application works with multiple MongoDB databases, adding a database name to a connection string only solves data routing. The system must also decide **whether to share or separate credentials**, **mapping converters**, and **transaction managers** so data is not written to the wrong place, permissions are not unintentionally widened, and transactions have clear boundaries.

This lesson belongs to the **Multiple databases** chapter of `SPRING_DATA_MONGODB`. The examples use Spring Data MongoDB to map documents, query via `MongoTemplate`/repositories, and manage indexes and transactions. The focus is on intentional configuration, verification through observable behaviors, and recognizing limits when two databases reside on the same or different clusters.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **MongoDB cluster**, **MongoClient**, **MongoDatabaseFactory**, **MongoTemplate**, **converter**, **repository**, and **MongoTransactionManager**.
2. Choose to share a `MongoClient` when databases use the same credentials, or separate clients when different access identities are required.
3. Configure two sets of MongoDB beans with explicit names and bind repositories using the right `mongoTemplateRef`.
4. Create independent `MongoCustomConversions` and `MappingMongoConverter` beans when each database has different BSON storage conventions.
5. Select a transaction manager by name in `@Transactional`; explain why two managers do not automatically form an atomic distributed transaction.
6. Verify connectivity, permissions, serialization, target databases, and rollbacks to avoid silent misconfigurations.

## 2. Understanding the isolation layers

In a single-database application, Spring Boot typically auto-configures one `MongoClient`, `MongoDatabaseFactory`, `MongoTemplate`, and the corresponding repositories. As the number of databases grows, you must decide **which scope each component belongs to**.

```text
Application
├── Catalog (database: catalog_db)
│   ├── catalogMongoClient        -> credential: catalog_app
│   ├── catalogDatabaseFactory    -> catalog_db
│   ├── catalogMongoConverter     -> dedicated BSON mapping
│   ├── catalogMongoTemplate      -> catalog CRUD and queries
│   ├── CatalogRepository         -> bound to catalogMongoTemplate
│   └── catalogTransactionManager -> catalog transactions
│
└── Audit (database: audit_db)
    ├── auditMongoClient          -> credential: audit_app
    ├── auditDatabaseFactory      -> audit_db
    ├── auditMongoConverter       -> separate/default BSON mapping
    ├── auditMongoTemplate        -> audit CRUD and queries
    ├── AuditRepository           -> bound to auditMongoTemplate
    └── auditTransactionManager   -> audit transactions
```

| Component | Responsibility | When to separate? |
| --- | --- | --- |
| `MongoClient` | Connections, authentication, connection pool, sessions | When URI, cluster, credentials, TLS, or other connection attributes must be independent |
| `MongoDatabaseFactory` | Selects the logical database and supplies MongoDB interactions for templates/transactions | Typically each target database has its own factory |
| `MongoTemplate` | CRUD, query, aggregation, index, and mapping API for a database | Each database + converter combination needs its own template |
| `MongoCustomConversions` | Converters between Java types and BSON | When two databases use different conversion rules |
| `MappingMongoConverter` | Object/document mapping, field names, `_id`, DBRef | When mapping context or custom conversions differ |
| `MongoRepository` | Domain-oriented data access abstraction | Bind each repository group to the right template |
| `MongoTransactionManager` | Manages transactions and sessions through a MongoDB factory | When transactions are needed per database/client scope |

**Distinction:** a database name is not a security mechanism. `MongoDatabaseFactory(client, "catalog_db")` only selects the target database; read/write permissions are governed by the connection's credentials and MongoDB RBAC.

## 3. Deciding whether to share or separate clients

Not every multi-database system needs two `MongoClient` instances.

| Context | Usually appropriate choice | Reason |
| --- | --- | --- |
| Two databases on the same cluster, same account and connection policy | One `MongoClient`, two factories/templates | Reuses the connection pool, avoids excess connections |
| Same cluster, but each database has its own account and permissions | Two `MongoClient`s, two factories/templates | Each client carries separate authentication, enforcing least privilege |
| Two independent MongoDB clusters | Two `MongoClient`s, two factories/templates | Separate topology, pools, credentials, and failure domains |
| Two databases with identical BSON conversion conventions | Can share appropriately managed mapping components | Reduces configuration, though DBRef and mapping context must be checked |
| Two databases with different converters, field names, or data types | Separate converters/mapping contexts | Prevents a converter from affecting entities belonging to another database |
| Single-document operations only and no multi-document transactions needed | No need to create a transaction manager | Single-document writes are already atomic at the document level |
| Two business flows requiring independent transactions | Two explicitly named managers | Prevents selecting the wrong transaction manager |

When two `MongoClient`s target the same cluster with two different credentials, MongoDB cannot dynamically switch a single `MongoClient`'s account from one request to another. Separating clients is the clear and controllable choice.

### 3.1. `authSource` differs from the operational database

For example, a URI may carry:

```text
mongodb://catalog_app:***@mongo-a:27017,mongo-b:27017/
  ?replicaSet=rs0&authSource=admin&tls=true
```

- `authSource=admin`: the MongoDB database storing authentication info for `catalog_app`, **not** a database automatically permitted for writes.
- `catalog_db`: the business database selected when creating `MongoDatabaseFactory`.
- Roles such as `readWrite` on `catalog_db` are what grant operational permissions. An account with `readWrite` on one database does not inherently have rights on another database.

Store secrets in environment variables or a secret manager. Never commit URIs containing usernames/passwords and never log raw URIs. When URL-encoding passwords in a URI, ensure special characters are properly encoded.

## 4. Configuring two databases with Spring Boot and Spring Data MongoDB

Consider an order management system:

- `catalog_db` stores `orders`, must read/write business data, and uses an `Amount` monetary type.
- `audit_db` stores `audit_events`, primarily append/audit, with simple entity mapping.
- Each database has its own credentials. The example uses **two singleton MongoClients**.

The Java snippets below illustrate the Spring Data MongoDB pattern using the **imperative driver**, Java 17+, and matching Spring Boot/Spring Data versions. For other API versions, check constructor signatures and your project's auto-configuration setup.

### 4.1. Declaring URIs and database names

```yaml
# application.yml
app:
  mongo:
    catalog:
      uri: ${CATALOG_MONGODB_URI}
      database: catalog_db
    audit:
      uri: ${AUDIT_MONGODB_URI}
      database: audit_db
```

Deployment environment variables hold the actual URIs, with appropriately scoped credentials and required TLS/replica-set options. Do not use a default URI pointing to `admin` and assume it can write to every database.

When declaring multiple `MongoClient` and `MongoTemplate` beans manually, check whether Spring Boot still auto-creates any default MongoDB beans. Leftover or colliding beans can cause `@Autowired` ambiguity or route repositories to the wrong database. The examples below use `@Qualifier` and `mongoTemplateRef` intentionally.

### 4.2. Dedicated model and converters for catalog

Catalog stores the monetary type `Amount` as BSON `Decimal128`. Instead of letting `Amount` map to a nested subdocument like `{value: ...}`, we use two custom converters.

```java
// com.example.catalog.model.Amount
package com.example.catalog.model;

import java.math.BigDecimal;

public record Amount(BigDecimal value) {}
```

Two converters (placed in the catalog configuration package):

```java
package com.example.catalog.config;

import com.example.catalog.model.Amount;
import java.math.BigDecimal;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class AmountWriteConverter
        implements Converter<Amount, Decimal128> {

    @Override
    public Decimal128 convert(Amount amount) {
        return new Decimal128(amount.value());
    }
}
```

```java
package com.example.catalog.config;

import com.example.catalog.model.Amount;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class AmountReadConverter
        implements Converter<Decimal128, Amount> {

    @Override
    public Amount convert(Decimal128 value) {
        return new Amount(value.bigDecimalValue());
    }
}
```

`@WritingConverter`/`@ReadingConverter` help Spring Data recognize conversion direction, especially when both source and target types can appear in MongoDB mapping. Because they are registered specifically for catalog, fields of similar types in audit will not unexpectedly follow the same BSON storage rules.

### 4.3. Catalog bean set

```java
package com.example.catalog.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.data.mongodb.core.convert.DefaultDbRefResolver;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackages = "com.example.catalog.repository",
    mongoTemplateRef = "catalogMongoTemplate"
)
public class CatalogMongoConfig {

    @Bean(name = "catalogMongoClient", destroyMethod = "close")
    MongoClient catalogMongoClient(
            @Value("${app.mongo.catalog.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean("catalogDatabaseFactory")
    MongoDatabaseFactory catalogDatabaseFactory(
            @Qualifier("catalogMongoClient") MongoClient client,
            @Value("${app.mongo.catalog.database}") String database) {
        return new SimpleMongoClientDatabaseFactory(client, database);
    }

    @Bean("catalogConversions")
    MongoCustomConversions catalogConversions() {
        return new MongoCustomConversions(List.of(
            new AmountWriteConverter(),
            new AmountReadConverter()
        ));
    }

    @Bean("catalogMappingContext")
    MongoMappingContext catalogMappingContext(
            @Qualifier("catalogConversions")
            MongoCustomConversions conversions) {
        MongoMappingContext context = new MongoMappingContext();
        context.setSimpleTypeHolder(conversions.getSimpleTypeHolder());
        return context;
    }

    @Bean("catalogMongoConverter")
    MappingMongoConverter catalogMongoConverter(
            @Qualifier("catalogDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("catalogMappingContext")
            MongoMappingContext context,
            @Qualifier("catalogConversions")
            MongoCustomConversions conversions) {

        MappingMongoConverter converter = new MappingMongoConverter(
            new DefaultDbRefResolver(factory), context
        );
        converter.setCustomConversions(conversions);
        return converter;
    }

    @Bean("catalogMongoTemplate")
    MongoTemplate catalogMongoTemplate(
            @Qualifier("catalogDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("catalogMongoConverter")
            MappingMongoConverter converter) {
        return new MongoTemplate(factory, converter);
    }

    @Bean("catalogTransactionManager")
    MongoTransactionManager catalogTransactionManager(
            @Qualifier("catalogDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Key points of this wiring:

- `catalogMongoClient` owns the connection and credentials. It is a singleton bean that will be closed when the application context shuts down.
- `catalogDatabaseFactory` is bound precisely to that client and the database name `catalog_db`.
- `catalogMongoConverter` uses **catalogConversions** and **catalogMappingContext**. It does not accidentally inject another database's default converter.
- `catalogMongoTemplate` uses the factory and converter declared right alongside it.
- `catalogTransactionManager` uses the **same factory** as the template, ensuring sessions are scoped properly during transactions.
- `@EnableMongoRepositories` scans only the catalog repository package, and `mongoTemplateRef` points to the right template.

Creating a dedicated converter provides full control, but also requires keeping mapping configuration, custom conversions, and index handling in sync. If your application has specialized mapping settings (naming strategy, metadata, type mapper, DBRef, conversions), do not copy an old converter to a new template while overlooking differences.

### 4.4. Audit bean set

Audit does not need catalog's `Amount` converter. Here we still create an independent converter with an empty custom conversion list; later, audit can register converters tailored to the audit schema.

```java
package com.example.audit.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import java.util.List;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;
import org.springframework.data.mongodb.core.convert.DefaultDbRefResolver;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(
    basePackages = "com.example.audit.repository",
    mongoTemplateRef = "auditMongoTemplate"
)
public class AuditMongoConfig {

    @Bean(name = "auditMongoClient", destroyMethod = "close")
    MongoClient auditMongoClient(
            @Value("${app.mongo.audit.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean("auditDatabaseFactory")
    MongoDatabaseFactory auditDatabaseFactory(
            @Qualifier("auditMongoClient") MongoClient client,
            @Value("${app.mongo.audit.database}") String database) {
        return new SimpleMongoClientDatabaseFactory(client, database);
    }

    @Bean("auditConversions")
    MongoCustomConversions auditConversions() {
        return new MongoCustomConversions(List.of());
    }

    @Bean("auditMappingContext")
    MongoMappingContext auditMappingContext(
            @Qualifier("auditConversions")
            MongoCustomConversions conversions) {
        MongoMappingContext context = new MongoMappingContext();
        context.setSimpleTypeHolder(conversions.getSimpleTypeHolder());
        return context;
    }

    @Bean("auditMongoConverter")
    MappingMongoConverter auditMongoConverter(
            @Qualifier("auditDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("auditMappingContext")
            MongoMappingContext context,
            @Qualifier("auditConversions")
            MongoCustomConversions conversions) {

        MappingMongoConverter converter = new MappingMongoConverter(
            new DefaultDbRefResolver(factory), context
        );
        converter.setCustomConversions(conversions);
        return converter;
    }

    @Bean("auditMongoTemplate")
    MongoTemplate auditMongoTemplate(
            @Qualifier("auditDatabaseFactory")
            MongoDatabaseFactory factory,
            @Qualifier("auditMongoConverter")
            MappingMongoConverter converter) {
        return new MongoTemplate(factory, converter);
    }

    @Bean("auditTransactionManager")
    MongoTransactionManager auditTransactionManager(
            @Qualifier("auditDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

**Do not create two MongoClients just to use two database names** if they share the same cluster, identity, and connection settings. In that case, you can keep **one client** and declare two `SimpleMongoClientDatabaseFactory(client, databaseName)` beans, two templates, and only the converters/transaction managers actually needed.

### 4.5. Variant sharing a single MongoClient

If catalog and audit are on the same cluster, use the same account authorized on both databases, and share connection parameters:

```java
@Bean(name = "sharedMongoClient", destroyMethod = "close")
MongoClient sharedMongoClient(
        @Value("${app.mongo.shared.uri}") String uri) {
    return MongoClients.create(uri);
}

@Bean("catalogDatabaseFactory")
MongoDatabaseFactory catalogDatabaseFactory(
        @Qualifier("sharedMongoClient") MongoClient client) {
    return new SimpleMongoClientDatabaseFactory(client, "catalog_db");
}

@Bean("auditDatabaseFactory")
MongoDatabaseFactory auditDatabaseFactory(
        @Qualifier("sharedMongoClient") MongoClient client) {
    return new SimpleMongoClientDatabaseFactory(client, "audit_db");
}
```

This is an **alternative variant** replacing the two `MongoClient` creation methods and two factories above; do not declare duplicate bean names simultaneously in the same application. The two factories remain separate in their default databases, while the shared client uses the same pool and credentials. Sharing a client **does not mean** transactions across the two factories automatically join into a single transaction.

## 5. Accurate repository and MongoTemplate routing

### 5.1. Two entity and repository groups

Minimal catalog entity example:

```java
package com.example.catalog.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class CatalogOrder {

    @Id
    private String id;

    private Amount amount;
    private String status;

    // Constructors, getters, setters...
}
```

```java
package com.example.catalog.repository;

import com.example.catalog.model.CatalogOrder;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogOrderRepository
        extends MongoRepository<CatalogOrder, String> {
}
```

Audit entity and repository:

```java
package com.example.audit.model;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("audit_events")
public class AuditEvent {

    @Id
    private String id;

    private String action;
    private Instant createdAt;

    // Constructors, getters, setters...
}
```

```java
package com.example.audit.repository;

import com.example.audit.model.AuditEvent;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AuditEventRepository
        extends MongoRepository<AuditEvent, String> {
}
```

Because the two configurations in the previous section use **non-overlapping** `basePackages`, each repository is bound to the correct `MongoTemplate`. `@Document(collection = ...)` only specifies the **collection**; it does not choose the MongoDB database or `MongoClient`.

### 5.2. Injecting `MongoTemplate` with `@Qualifier`

```java
package com.example.reporting;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class DataDiagnosticsService {

    private final MongoTemplate catalog;
    private final MongoTemplate audit;

    public DataDiagnosticsService(
            @Qualifier("catalogMongoTemplate")
            MongoTemplate catalog,
            @Qualifier("auditMongoTemplate")
            MongoTemplate audit) {
        this.catalog = catalog;
        this.audit = audit;
    }

    public String describeTargets() {
        return "Catalog=" + catalog.getDb().getName()
             + ", Audit=" + audit.getDb().getName();
    }
}
```

The expected output is `Catalog=catalog_db, Audit=audit_db`. If both names appear identical, immediately inspect the factories or properties.

When multiple `MongoTemplate` or `MongoDatabaseFactory` beans exist in the context, never inject by type alone:

```java
// Ambiguous which bean is chosen when multiple MongoTemplates exist:
// public SomeService(MongoTemplate template) { ... }
```

You can mark `@Primary` on a bean that truly acts as a default. However, **explicit names and `@Qualifier`** are usually better suited for sensitive data-processing layers or systems with multiple peer databases.

## 6. Converters: isolating BSON conventions per database

### 6.1. How converters affect data representation

A `MappingMongoConverter` controls how Java objects become BSON `Document`s and vice versa. For example:

| Domain field | Catalog with custom conversion | Audit with default/dedicated mapping |
| --- | --- | --- |
| `Amount(BigDecimal)` | Stored as BSON `Decimal128` | Does not necessarily have this type |
| `Instant` | Per selected date/time convention | May use a different UTC convention or legacy format |
| `@Field("...")` | Per catalog entity/annotation | Per audit entity |
| `@Id` | Maps catalog entity ID | Maps audit entity ID |
| DBRef and target database | Needs corresponding resolver/factory | Needs corresponding resolver/factory |

If `catalogMongoConverter` is accidentally wired into `auditMongoTemplate`, catalog custom converters could be applied to audit. The risk is even greater when a converter targets a common type like `String` or `Date`: it can alter many unrelated fields.

### 6.2. Synchronizing conversions with the mapping context

An easily overlooked detail in manual configuration is that `MongoMappingContext` also needs to know which types count as **simple types**. In the example:

```java
MongoCustomConversions conversions = new MongoCustomConversions(
    List.of(new AmountWriteConverter(), new AmountReadConverter())
);

MongoMappingContext context = new MongoMappingContext();
context.setSimpleTypeHolder(conversions.getSimpleTypeHolder());

MappingMongoConverter converter =
    new MappingMongoConverter(new DefaultDbRefResolver(factory), context);
converter.setCustomConversions(conversions);
```

If you only register custom conversions on the converter and skip the mapping context, complex-type discovery/mapping may behave inconsistently. In production configurations, keep the context, custom conversions, and converter aligned.

### 6.3. When can converters be shared?

Only consider sharing a converter when:

- Both databases share the exact same schema conventions, custom conversions, naming, and type mapping.
- Any DBRef references do not depend on the target factory or have a clear resolution strategy.
- Reading and writing both entity types has been tested and confirmed to have no cross-impact.
- Any converter change for database A will be reviewed for impact on database B.

Even when conventions match, **separate** converter configurations are often easier to govern for two independently evolving bounded contexts. Conversely, splitting converters solely because there are two database names can add configuration boilerplate without business benefit.

### 6.4. Avoiding overlapping automatic index creation

Two templates can manage collections with the same name (for example, each database has `orders`), yet those are **two distinct namespaces**. `indexOps` must be invoked on the target template:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

catalogMongoTemplate.indexOps("orders")
    .ensureIndex(new Index().on("status", Sort.Direction.ASC));

auditMongoTemplate.indexOps("audit_events")
    .ensureIndex(new Index().on("createdAt", Sort.Direction.DESC));
```

Spring Data MongoDB does not guarantee that every configuration will auto-create indexes in production. When index management is governed by migrations, use explicit deployment scripts/steps and verify indexes on the corresponding database.

## 7. Transaction managers: separating transaction boundaries properly

### 7.1. Which factory does a MongoTransactionManager bind to?

`MongoTransactionManager` manages transactions using a MongoDB `ClientSession` through a `MongoDatabaseFactory`. `MongoTemplate` participates in Spring-managed transactions when the operation's factory/session is compatible with the resource bound to the transaction context.

In our example, we have:

```java
@Bean("catalogTransactionManager")
MongoTransactionManager catalogTransactionManager(
        @Qualifier("catalogDatabaseFactory")
        MongoDatabaseFactory catalogFactory) {
    return new MongoTransactionManager(catalogFactory);
}

@Bean("auditTransactionManager")
MongoTransactionManager auditTransactionManager(
        @Qualifier("auditDatabaseFactory")
        MongoDatabaseFactory auditFactory) {
    return new MongoTransactionManager(auditFactory);
}
```

These two managers make clear which transactions belong to catalog and which belong to audit. They do **not** automatically coordinate commits/rollbacks into a single shared distributed transaction.

If the application needs multi-document transactions, the MongoDB deployment must support them (a properly configured replica set or sharded cluster). A standalone `mongod` is not an equivalent substitute for testing transactions.

### 7.2. Selecting the manager with `@Transactional`

```java
package com.example.catalog.service;

import com.example.catalog.repository.CatalogOrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogOrderService {

    private final CatalogOrderRepository orders;

    public CatalogOrderService(CatalogOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "catalogTransactionManager")
    public void saveCatalogOrder(CatalogOrder order) {
        orders.save(order);

        // Additional catalog operations can participate in this same transaction.
    }
}
```

Audit service example:

```java
package com.example.audit.service;

import com.example.audit.repository.AuditEventRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditEventService {

    private final AuditEventRepository events;

    public AuditEventService(AuditEventRepository events) {
        this.events = events;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public void appendEvent(AuditEvent event) {
        events.save(event);
    }
}
```

In actual code, add imports for `CatalogOrder` or `AuditEvent` from the appropriate model package. If two transaction managers coexist and a method only specifies `@Transactional` without naming a manager, Spring needs a default manager selection mechanism; otherwise bean resolution can fail or select an unintended manager.

**Execution requirement:** Spring's transaction proxy does not intercept self-invocations such as `this.saveCatalogOrder(...)` within the same instance. Invoke transactional methods through a Spring bean, verify which transaction manager is selected, and design exception handling carefully.

### 7.3. Catalog transactions do not cover audit

Consider this flow:

```java
@Transactional(transactionManager = "catalogTransactionManager")
public void processOrder(CatalogOrder order, AuditEvent event) {
    catalogOrderRepository.save(order);
    auditEventRepository.save(event);
}
```

With **two separate MongoClients/factories/transaction managers** as configured above, `catalogOrderRepository` can participate in the catalog transaction, whereas `auditEventRepository` **does not automatically share the same MongoDB session or transaction**.

If the audit write succeeds and catalog rolls back, an orphan audit record may remain; or vice versa. You cannot assume both are atomic simply because they are inside the same `@Transactional` method.

Even when both databases reside on the same MongoDB cluster, two templates configured with **two different factories** do not automatically join the same transaction of one factory. MongoDB does support transactions spanning multiple collections/databases **within the same compatible deployment** when using the **same session**; to achieve that, you must explicitly design how the session/factory is shared or use the appropriate session/transaction APIs, and verify end-to-end. Across **two independent clusters**, a single MongoDB transaction cannot commit atomically on both clusters.

### 7.4. When consistency across multiple databases is needed

When you want to save an order and emit an audit/log record in another database:

- **Two independent steps:** accept eventual consistency with controlled retries/idempotency if the business rules allow it.
- **Transactional outbox:** save the order and an outbox record within the **same catalog transaction**; another process reads the outbox, writes to audit, and marks delivery status. The audit writer must be idempotent because an event may be redelivered.
- **Same cluster, same session:** if cross-database atomicity is strictly required, design and test a MongoDB cross-database transaction with a shared session rather than assuming two transaction managers coordinate automatically.
- **Two clusters:** use a saga/compensating action pattern or outbox; do not treat `ChainedTransactionManager` or consecutive commits as an atomic distributed transaction.

A simple outbox flow:

```mermaid
flowchart LR
    A["HTTP Create Order"] --> B["Catalog Transaction"]
    B --> C["Save order"]
    B --> D["Save outbox event"]
    D --> E["Outbox publisher"]
    E --> F["Audit database"]
    F --> G["Idempotent write by eventId"]
```

Saving the `order` and the `outbox` record must happen inside the same catalog transaction. Forwarding the event to audit occurs afterward, with clear retry and deduplication handling.

## 8. Access permissions and operating multiple MongoClients

### 8.1. Least privilege per database

Design minimal roles:

| Account | Accessible database | Example permissions |
| --- | --- | --- |
| `catalog_app` | `catalog_db` | `readWrite` if business logic needs both reads and writes |
| `audit_app` | `audit_db` | Insert/read privileges matching audit policy |
| Migration/admin | Namespaces needing schema/index changes | Separate admin privileges; do not share credentials with runtime apps |

`MongoTemplate` only selects a database **in application logic**; if an account has overly broad permissions, injecting the wrong template can still write to the wrong database without being blocked by the server. Therefore, **correct bean names** and **proper RBAC** complement each other.

Separate credentials also mean rotating catalog's secret does not forcibly impact audit, though two separate connection pools increase the number of connections the cluster must maintain. Monitor connection counts, pool exhaustion, timeouts, and how one cluster's failure impacts requests using the other cluster.

### 8.2. Lifecycle and connection pools

- `MongoClient` is thread-safe and designed for **reuse**. Never create a new client per request or per repository operation.
- Declare singleton beans and let Spring close them on application shutdown (`destroyMethod = "close"`).
- When sharing a cluster and credentials, sharing a client generally reduces pool and socket counts.
- Two separate clients have separate pools, topology monitoring, and connection limits. Configure max pool size, timeouts, TLS, and retries according to workload rather than copying arbitrary values.
- When one database becomes unavailable, configure appropriate timeouts and circuit breakers so the entire application does not stall.

### 8.3. Configuration checklist to prevent routing mistakes

A checklist when adding another database:

1. Use clear names: `catalogMongoClient`, `catalogDatabaseFactory`, `catalogMongoConverter`, `catalogMongoTemplate`, `catalogTransactionManager`.
2. Follow the same pattern for audit, avoiding bean name collisions.
3. Use `@Qualifier` on constructors and `mongoTemplateRef` on `@EnableMongoRepositories`.
4. Never overlap repository scans between two configuration classes.
5. Verify `@Document` points to the right collection and entity converter.
6. Do not rely on default `spring.data.mongodb.database` once two separate factories are configured.
7. Test RBAC with the actual deployment credentials.
8. If using transactions, bind each transaction manager to the right factory and deploy on a MongoDB topology supporting transactions.

## 9. Testing configuration and diagnosing issues

### 9.1. Smoke test for target databases and converters

An integration test can inject both templates via qualifiers and compare database names:

```java
@SpringBootTest
class MongoWiringTest {

    @Autowired
    @Qualifier("catalogMongoTemplate")
    MongoTemplate catalog;

    @Autowired
    @Qualifier("auditMongoTemplate")
    MongoTemplate audit;

    @Test
    void templatesPointToDifferentDatabases() {
        assertThat(catalog.getDb().getName()).isEqualTo("catalog_db");
        assertThat(audit.getDb().getName()).isEqualTo("audit_db");
        assertThat(catalog.getConverter())
            .isNotSameAs(audit.getConverter());
    }
}
```

This is a test skeleton (add JUnit/AssertJ imports and test environment URI configuration). If using the single-client variant, still verify two distinct databases; do not require two distinct `MongoClient`s.

Next, run an integration test against two real test MongoDB databases:

- Write a `CatalogOrder` with `Amount(new BigDecimal("12.34"))` through the catalog repository.
- Read the raw BSON document and confirm the amount field is `Decimal128`.
- Write and read an `AuditEvent` in `audit_db`, verifying independence from catalog converters.
- Attempt a direct operation on audit using catalog credentials (in a test environment with separate roles), expecting rejection if RBAC is configured properly.
- Perform two catalog operations in a transaction, intentionally throw an error, and verify rollback; repeat independently for audit transactions if used.
- Do not assume an exception thrown after writing to audit will roll back audit when the transaction manager belongs only to catalog.

### 9.2. Common troubleshooting table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` for `MongoTemplate` | Two templates of the same type without qualifier/default | Use explicit bean names and `@Qualifier` |
| Repository saves to the wrong database | Overlapping package scan or wrong `mongoTemplateRef` | Separate packages and verify repository-template mapping |
| `MongoSecurityException` / unauthorized | Incorrect credentials/`authSource`/MongoDB roles | Verify URI, per-database roles, and secret configuration |
| `ConverterNotFoundException` or unexpected BSON schema | Wrong converter used or missing custom conversions | Check converter beans, reading/writing converters, and mapping context |
| Money field stored as nested document | `Amount → Decimal128` converter not applied | Check converter registration and actual BSON documents |
| `NoSuchBeanDefinitionException` for transaction manager | Wrong name in `@Transactional` or missing bean | Create the proper `MongoTransactionManager` and check context |
| Transaction rejected | Standalone mongod, unsupported version/topology, or misconfigured session | Use a replica set/sharded cluster supporting transactions and connect properly |
| One database rolls back while the other commits | Two separate factories/transactions without a shared session | Redesign atomicity, use a shared session where applicable, or use an outbox |
| Connection count spikes sharply | Creating `MongoClient` per request or too many pools | Reuse singletons and share a client when credentials match |
| Unusually slow queries | Routing hits the right database, but index wasn't created in that namespace | Check `indexOps` and `explain("executionStats")` on the right database |

### 9.3. Inspecting in `mongosh`

Log in with the appropriate environment account (avoid putting secrets into shell history commands whenever possible), then inspect each database, collection, and index separately:

```javascript
use catalog_db

db.getName();
db.orders.getIndexes();
db.orders.find({ status: "NEW" }).explain("executionStats");
```

And similarly:

```javascript
use audit_db

db.getName();
db.audit_events.getIndexes();
db.audit_events.find().sort({ createdAt: -1 }).limit(5);
```

When the application logs the target database name for diagnostics, log only the logical database name, bean/operation, and duration; never log URIs with credentials, tokens, or sensitive document contents.

## 10. Reactive stack, repositories, and differences to note

The examples in this lesson use **imperative** `MongoTemplate` and `MongoTransactionManager`. If an application uses **Reactive Spring Data MongoDB**, the bean types differ:

- The reactive driver uses `com.mongodb.reactivestreams.client.MongoClient`.
- Data access uses `ReactiveMongoTemplate` and `ReactiveMongoDatabaseFactory`.
- Transactions use `ReactiveMongoTransactionManager`, bound to **Reactor Context** instead of the imperative stack's thread-bound transactions.
- Repositories use `@EnableReactiveMongoRepositories` configured with the corresponding reactive template.

Do not share an imperative template's `MongoTransactionManager` with a reactive pipeline. If both stacks exist, keep each stack's scope and transaction context separate.

Likewise, with multiple repository modules, do not set `basePackages` too broadly. A package scanned by two `@EnableMongoRepositories` configurations can create duplicate beans or bind the wrong `MongoTemplate`.

## 11. Scenario exercises

### Scenario A: Same cluster, same account

A reporting application reads `sales_db` and `customer_db` using the same MongoDB user with read privileges. Use **one `MongoClient`**, create **two `MongoDatabaseFactory` instances** and templates pointing to each database, and only create separate converters if mapping conventions differ.

### Scenario B: Two separate credentials

An order system stores data in `orders_db`, while audit logs require a lower-privilege account in `audit_db`. Use **two `MongoClient` instances** with URIs from a secret manager, two factories, two templates, and two repository sets. Verify that orders credentials cannot write to audit if policy requires privilege separation.

### Scenario C: Audit requires a different BSON format

Database A stores money as `Decimal128`, while database B ingests JSON documents from a legacy system with date fields stored as strings. Create **separate `MongoCustomConversions`/`MappingMongoConverter` beans** for the two domains, write read/write tests through the right template, and inspect the resulting BSON values.

### Scenario D: Rolling back order and audit together

Two services use two separate transaction managers; one saves an order and another saves an audit record. `@Transactional("catalogTransactionManager")` **does not guarantee** both parts roll back together. If they share a cluster and genuinely require cross-database atomicity, design around a shared MongoDB session; if they reside on different clusters or eventual consistency is acceptable, use a **transactional outbox** with idempotency.

### Scenario E: Adding a third database

Before copying configuration, answer:

1. Does the new database have different credentials or a different cluster?
2. Are schema conversions different?
3. Which repository package owns it?
4. Do business operations require multi-document transactions?
5. Are any operations expected to span databases transactionally?
6. What indexes, monitoring, and pool limits are required?

Answering these questions determines which parts of the configuration need to be duplicated and which can be shared.

## 12. Implementation checklist

| Item | What to verify |
| --- | --- |
| Connection | Environment-specific URI, TLS/replica set options, no leaked secrets |
| Authentication | Correct `authSource`, sufficient yet minimal roles |
| Factory | Correct `databaseName`, client matches the intended credentials |
| Template | Uses the right factory and converter |
| Repository | Disjoint package scans, accurate `mongoTemplateRef` |
| Conversion | Custom conversions and simple type holder synchronized, BSON round trip verified |
| Transaction | Manager matches factory, no mistaken atomicity across two scopes |
| Auto-configuration | No leftover default `MongoClient`/template/repository causing interference |
| Data correctness | Read/write and rollback tests on the target databases |
| Production | Monitor connection pools, indexes, retries, timeouts, and errors per database |

The core rule of practice is to **separate along boundaries that genuinely differ**: credentials by privilege, factories by target database, converters by BSON convention, and transaction managers by session/transaction scope. Every `MongoTemplate` and repository must be explicitly wired to the right combination.

## References

- Spring Data MongoDB Reference — [Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html)
- Spring Data MongoDB Reference — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- Spring Data MongoDB Reference — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html)
- Spring Data MongoDB Reference — [MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html)
- Spring Data MongoDB Reference — [Client Session Support and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- MongoDB Manual — [Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- MongoDB Manual — [Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
