# Multiple MongoClient, MongoDatabaseFactory, and MongoTemplate Instances

In Spring Data MongoDB, an application can access multiple databases by configuring connection beans and binding each business flow to the right `MongoTemplate` or repository. This lesson belongs to the **Multiple databases** chapter of **SPRING_DATA_MONGODB**: using Spring Data MongoDB to connect, map documents, and manipulate data through `MongoTemplate`/repositories, while managing queries, transactions, testing, and performance.

## 1. Objectives and real-world scenario

Suppose an e-commerce service has:

- `orders_db`: orders requiring fast transactions and strict write permissions.
- `audit_db`: audit events with a different retention period and access policy.

The two databases may reside in the **same MongoDB deployment** or on **two independent deployments**. In that case, the application must choose the right database for each operation, configure repositories clearly, manage connection lifecycles, and understand transaction boundaries.

After this lesson, learners will be able to:

1. Distinguish the responsibilities of `MongoClient`, `MongoDatabaseFactory`, and `MongoTemplate`.
2. Decide when one or multiple `MongoClient` instances are needed.
3. Configure two databases with named beans and `@Qualifier`.
4. Bind each `MongoRepository` group to the right `MongoTemplate` using `mongoTemplateRef`.
5. Identify data routing errors, manage connection pools, transactions, and test the configuration.

## 2. How do the three configuration layers work together?

| Component | Role | Important scope |
| --- | --- | --- |
| `com.mongodb.client.MongoClient` | Driver client, manages connections, connection pool, TLS/auth config, server selection, and sessions | Points to a deployment/cluster; can access multiple databases in that deployment |
| `org.springframework.data.mongodb.MongoDatabaseFactory` | Provides the default `MongoDatabase` object from a client and database name | Binds one default database to a client; can obtain another database via `getMongoDatabase(String)` |
| `org.springframework.data.mongodb.core.MongoTemplate` | Spring Data API for CRUD, queries, aggregation, mapping, and exception translation | Each template uses one factory; regular operations go to the factory's default database |

Diagram of a configuration with two deployments:

```text
Orders Service / Orders Repository        Audit Service / Audit Repository
                 |                                      |
        ordersMongoTemplate                      auditMongoTemplate
                 |                                      |
     ordersMongoDatabaseFactory               auditMongoDatabaseFactory
                 |                                      |
          ordersMongoClient                         auditMongoClient
                 |                                      |
      Cluster A / orders_db                    Cluster B / audit_db
```

**Note:** `MongoClient` does not represent a single database. One client can open `getDatabase("orders_db")` and `getDatabase("audit_db")` on the same deployment. If both databases are on the same cluster, creating multiple clients to the same server usually increases connection pools and resources unnecessarily. `MongoTemplate` is typically registered as a singleton and can be reused across requests.

### Choosing the right topology

| Context | Typical number of clients | Typical number of factories/templates |
| --- | --- | --- |
| Two databases in the same cluster, same connection config | 1 shared client | 2 factories + 2 templates |
| Two independent clusters, different URIs/credentials | 2 clients | 2 factories + 2 templates |
| Multiple databases with different mapping configs | Depends on deployment | Separate factories and templates; consider separate converters/mapping contexts |
| Many dynamically created tenants | Avoid automatically creating a separate client per tenant | Need a per-tenant database selection strategy, cache/lifecycle management, and access control |

## 3. Configuring two MongoClients for two deployments

The example below uses Spring Boot with the **synchronous driver** (`com.mongodb.client.MongoClient`) and Spring Data MongoDB. A `spring-boot-starter-data-mongodb` dependency compatible with the project's Spring Boot version is required. Two test MongoDB servers are assumed to run on ports 27017 and 27018; in production, obtain URIs from environment variables or a secret manager.

### 3.1. Declaring settings in application.yml

```yaml
app:
  mongo:
    orders:
      uri: ${ORDERS_MONGODB_URI:mongodb://localhost:27017}
      database: orders_db
    audit:
      uri: ${AUDIT_MONGODB_URI:mongodb://localhost:27018}
      database: audit_db
```

`app.mongo.*` is a **custom namespace**; Spring Boot does not auto-generate templates for the two groups from this namespace. We will declare the beans ourselves. In a real environment, the URI should contain appropriate authentication/TLS settings, never hard-code passwords in the repository, and never log URIs containing credentials.

### 3.2. Declaring clients, factories, and templates

```java
package com.example.multimongo.config;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.SimpleMongoClientDatabaseFactory;

@Configuration(proxyBeanMethods = false)
public class MultiMongoConfig {

    @Bean(name = "ordersMongoClient", destroyMethod = "close")
    MongoClient ordersMongoClient(
            @Value("${app.mongo.orders.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean(name = "auditMongoClient", destroyMethod = "close")
    MongoClient auditMongoClient(
            @Value("${app.mongo.audit.uri}") String uri) {
        return MongoClients.create(uri);
    }

    @Bean("ordersMongoDatabaseFactory")
    MongoDatabaseFactory ordersMongoDatabaseFactory(
            @Qualifier("ordersMongoClient") MongoClient client,
            @Value("${app.mongo.orders.database}") String dbName) {
        return new SimpleMongoClientDatabaseFactory(client, dbName);
    }

    @Bean("auditMongoDatabaseFactory")
    MongoDatabaseFactory auditMongoDatabaseFactory(
            @Qualifier("auditMongoClient") MongoClient client,
            @Value("${app.mongo.audit.database}") String dbName) {
        return new SimpleMongoClientDatabaseFactory(client, dbName);
    }

    @Bean("ordersMongoTemplate")
    MongoTemplate ordersMongoTemplate(
            @Qualifier("ordersMongoDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }

    @Bean("auditMongoTemplate")
    MongoTemplate auditMongoTemplate(
            @Qualifier("auditMongoDatabaseFactory")
            MongoDatabaseFactory factory) {
        return new MongoTemplate(factory);
    }
}
```

In this example:

- The two `MongoClient` beans own two connection pools and are closed by Spring when the application context stops, thanks to `destroyMethod = "close"`.
- The two `SimpleMongoClientDatabaseFactory` instances receive a **managed client** and a database name. The factory does not close the external client passed into it; client lifecycle belongs to the `MongoClient` beans.
- The two `MongoTemplate` instances use their corresponding factories. Bean names are part of the configuration contract: when renaming, you must update all related `@Qualifier` and `mongoTemplateRef` annotations.
- `@Qualifier` eliminates ambiguity when the context has two or more beans of the same type. You can add `@Primary` for a default group if the application truly needs it, but repositories should still point explicitly by name.

This example intentionally avoids using `spring.data.mongodb.uri` to specify both connections. If the project already has default MongoDB auto-configuration, check existing beans to avoid duplicate clients/templates or selecting the wrong connection path.

## 4. Using one MongoClient for multiple databases on the same cluster

If `orders_db` and `audit_db` both reside at `mongodb://localhost:27017` and can share the same authentication mechanism, we **do not need** a second `auditMongoClient`. Instead, create two factories on the same client:

```java
MongoClient sharedClient = MongoClients.create("mongodb://localhost:27017");

MongoDatabaseFactory ordersFactory =
        new SimpleMongoClientDatabaseFactory(sharedClient, "orders_db");
MongoDatabaseFactory auditFactory =
        new SimpleMongoClientDatabaseFactory(sharedClient, "audit_db");

MongoTemplate ordersTemplate = new MongoTemplate(ordersFactory);
MongoTemplate auditTemplate = new MongoTemplate(auditFactory);

// Example illustrating object relationships.
// In Spring: create sharedClient as a singleton @Bean, then inject it
// into two MongoDatabaseFactory @Beans; Spring handles close().
```

The snippet above illustrates the structure, **not** a complete `@Bean` configuration to copy-paste into section 3. When applying it, replace the corresponding client/factory beans in the configuration and ensure only one owner closes `sharedClient`. Do not call `close()` after every query or every request.

Sharing a client does not mean the two databases automatically share access permissions. Actual database access and permissions still depend on the MongoDB account in the connection string. If the two databases require different credentials or network policies, separate clients may still be needed even on the same cluster.

## 5. Routing MongoRepository to the right database

Creating two templates alone is not enough when the application uses `MongoRepository`. The default repository mechanism typically looks for a bean named `mongoTemplate` unless specified otherwise; therefore, `@EnableMongoRepositories` must be configured for **each separate repository package**.

Suppose the package structure is:

```text
com.example.multimongo
├── config
│   ├── MultiMongoConfig.java
│   ├── OrdersRepositoryConfig.java
│   └── AuditRepositoryConfig.java
├── orders
│   ├── model/OrderDoc.java
│   └── repository/OrderRepository.java
└── audit
    ├── model/AuditEventDoc.java
    └── repository/AuditEventRepository.java
```

Repository configuration for the orders database:

```java
package com.example.multimongo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
        basePackages = "com.example.multimongo.orders.repository",
        mongoTemplateRef = "ordersMongoTemplate"
)
public class OrdersRepositoryConfig {
}
```

Repository configuration for the audit database:

```java
package com.example.multimongo.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration(proxyBeanMethods = false)
@EnableMongoRepositories(
        basePackages = "com.example.multimongo.audit.repository",
        mongoTemplateRef = "auditMongoTemplate"
)
public class AuditRepositoryConfig {
}
```

Minimal documents and repositories for the two groups:

```java
// com.example.multimongo.orders.model.OrderDoc
@Document("orders")
public record OrderDoc(
        @Id String id,
        String customerId,
        long totalCents
) {}

// com.example.multimongo.orders.repository.OrderRepository
public interface OrderRepository
        extends MongoRepository<OrderDoc, String> {}

// com.example.multimongo.audit.model.AuditEventDoc
@Document("audit_events")
public record AuditEventDoc(
        @Id String id,
        String action,
        String entityId
) {}

// com.example.multimongo.audit.repository.AuditEventRepository
public interface AuditEventRepository
        extends MongoRepository<AuditEventDoc, String> {}
```

These declarations belong in separate Java files; add appropriate imports such as `org.springframework.data.annotation.Id`, `org.springframework.data.mongodb.core.mapping.Document`, and `org.springframework.data.mongodb.repository.MongoRepository`.

Thanks to `mongoTemplateRef`, calling `orderRepository.save(...)` will use `ordersMongoTemplate`, while `auditEventRepository.save(...)` will use `auditMongoTemplate`. Never scan the same repository package in both configurations, as this can create duplicate beans or bind the wrong template. If Spring Boot is auto-scanning repositories, restrict or disable overlapping auto-scans according to your application structure.

## 6. Using MongoTemplate directly in a service

Not every case needs a repository. For dynamic queries, aggregations, or bulk operations, a service can inject the exact template:

```java
package com.example.multimongo.orders.service;

import com.example.multimongo.orders.model.OrderDoc;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final MongoTemplate orders;

    public OrderQueryService(
            @Qualifier("ordersMongoTemplate") MongoTemplate orders) {
        this.orders = orders;
    }

    public OrderDoc findById(String id) {
        return orders.findById(id, OrderDoc.class);
    }

    public OrderDoc save(OrderDoc order) {
        return orders.save(order);
    }
}
```

To write audit records, inject `@Qualifier("auditMongoTemplate")` into the audit service. With two templates of the same type, a constructor accepting `MongoTemplate` without a qualifier typically throws `NoUniqueBeanDefinitionException` (or relies unexpectedly on `@Primary`). You can inject the `MongoOperations` interface instead of the concrete class when only business operations are needed.

**Data safety point:** `@Document("orders")` only specifies the collection, **not the database**. The template determines the target database. Two databases that both have an `orders` collection remain two independent datasets.

## 7. Transactions and consistency

When a business operation only updates data in `orders_db`, you can declare a `MongoTransactionManager` corresponding to the orders factory:

```java
@Bean("ordersTransactionManager")
MongoTransactionManager ordersTransactionManager(
        @Qualifier("ordersMongoDatabaseFactory")
        MongoDatabaseFactory factory) {
    return new MongoTransactionManager(factory);
}
```

Import `org.springframework.data.mongodb.MongoTransactionManager`; place the method above in a `@Configuration` class. In the service:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void updateOrder(/* input data */) {
    // Operations via ordersMongoTemplate / ordersRepository
    // participate in the properly configured transaction.
}
```

Keep these distinctions clear:

1. MongoDB multi-document transactions require a topology that supports transactions, such as a replica set or sharded cluster; a standalone MongoDB instance does not meet this requirement.
2. `MongoTransactionManager` manages sessions/transactions for its **corresponding factory**. If `auditMongoDatabaseFactory` also exists, adding `auditTransactionManager` does not automatically create a shared distributed transaction across both managers.
3. Writing an order on cluster A and an audit record on cluster B is **not atomic by default**. For example, saving the order successfully and then failing to write the audit record can leave two inconsistent states.
4. If reliability across multiple clusters is needed, consider an outbox, a message queue, idempotent retries, or compensating workflows. When both databases are on the same deployment, a transaction spanning multiple namespaces is only feasible if operations actually share a supported session/transaction; two separate templates/factories do not guarantee that automatically.

Do not place an unqualified `@Transactional` when the application has multiple transaction managers and no clear default manager. Declare named manager beans, specify `transactionManager` in the annotation, and test actual rollback against the intended topology.

## 8. Testing configuration and verifying connections

An integration test should verify **the right target database** and **that the right server is reachable**. The JUnit 5 example below runs when the two MongoDB instances from section 3 are ready:

```java
@SpringBootTest
class MultiMongoWiringTest {

    @Autowired
    @Qualifier("ordersMongoTemplate")
    MongoTemplate orders;

    @Autowired
    @Qualifier("auditMongoTemplate")
    MongoTemplate audit;

    @Test
    void templatesPointToExpectedDatabases() {
        assertEquals("orders_db", orders.getDb().getName());
        assertEquals("audit_db", audit.getDb().getName());
    }

    @Test
    void bothDeploymentsRespondToPing() {
        assertDoesNotThrow(() ->
                orders.getDb().runCommand(new org.bson.Document("ping", 1)));
        assertDoesNotThrow(() ->
                audit.getDb().runCommand(new org.bson.Document("ping", 1)));
    }
}
```

Import `@SpringBootTest`, `@Autowired`, `@Qualifier`, `@Test`, `MongoTemplate`, and JUnit 5 static assertions. `getDb().getName()` only checks the configured database name, whereas `runCommand(ping)` verifies connectivity to the deployment. For CI environments, use two test MongoDB instances or Testcontainers and supply dynamic URIs; avoid smoke tests that depend on production servers.

Additional business-level tests:

- Save an `OrderDoc` via `ordersMongoTemplate` and read it back from `orders_db`.
- Verify that the record does not appear in `audit_db`, even if collection names match.
- Save an `AuditEventDoc` via the audit repository and check document count or query `audit_db` directly.
- Test access denial if credentials lack write permission on the other database.
- When using transactions, test error cases that trigger rollback within the proper scope and cases where cross-cluster writes partially fail.

Checking the database via `db.getName()` is **not enough** to prove it points to the right cluster if both clusters have databases with the same name. When full proof is needed, inspect the URI configuration in the deployment environment and verify each deployment via ping or test-specific marker data.

## 9. Operations, performance, and security

### Connection pool and lifecycle

`MongoClient` is a heavy object designed for reuse; creating a client per request increases connections, monitoring threads, and handshake overhead. Use one singleton client per reasonable deployment/credential configuration, and share a client when two databases use the same cluster and authentication parameters. Monitor pool utilization, connection timeouts, server selection timeouts, and connection errors per client. When tuning the pool, configure consistently via the URI or `MongoClientSettings`.

When a factory is created from `new SimpleMongoClientDatabaseFactory(existingClient, dbName)`, the **passed-in client** must be closed by its owner (in the example, the Spring bean), without relying on the factory to close it. Conversely, a constructor taking a connection string may create its own client; when the factory owns that client, the client's closing lifecycle follows the factory. Avoid mixing both ownership models without a clear convention.

### Mapping, indexes, and migrations

Each template has its own default mapping setup when built directly from a factory. If the application uses custom converters, custom conversions, codecs, naming strategies, auditing, or index setup, verify whether they are applied to each template. Do not assume that customizations on the main `mongoTemplate` bean are automatically replicated to manually created templates. Indexes, seed data, and migrations must be verified on **each target database**.

### Access control and observability

Use MongoDB users with least-privilege permissions for the required databases; keep secrets out of source control. When configuring multiple clients, tag logs/metrics with logical labels such as `orders` and `audit`, while avoiding logging URIs with passwords. Configure read/write concerns, timeouts, and retries according to each system's SLA. When reporting errors, include the bean name and logical database for isolation without exposing credentials.

### Common errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` when injecting MongoTemplate | Multiple beans of the same type | Use `@Qualifier`; use `@Primary` only when a valid default exists |
| Repository fails to initialize, reporting missing `mongoTemplate` | `mongoTemplateRef` omitted when bean has a different name | Specify `mongoTemplateRef` for each repository group |
| Writes to an unexpected database | Overlapping repository package scan or wrong template injected | Separate packages, verify bean names and db names in integration tests |
| Growing number of sockets/resources | Multiple clients pointing to the same cluster | Reuse a shared client if connection configs are compatible |
| Cannot start MongoDB transaction | Unsupported MongoDB topology or wrong manager selected | Use a proper replica set/sharded cluster and bind the manager to the right factory |
| Transaction succeeds on one side only | Two independent clusters/factories | Design idempotency, outbox, or an appropriate coordination mechanism |
| Authentication error only on the second database | Wrong `authSource`, credentials, or permissions | Check the URI and roles of the separate account |
| Mapping or indexes differ from expectations | Second template lacks converter/index configuration | Apply separate mapping/index configurations and test |

## 10. Project adoption checklist

1. Draw the database → deployment → credential diagram before deciding the number of `MongoClient` instances.
2. Name client, factory, and template beans clearly; maintain a one-way relationship: client → factory → template.
3. Bind each repository package with `mongoTemplateRef`; in services, use `@Qualifier` when injecting templates.
4. Manage client lifecycle as a singleton and close it exactly once at shutdown.
5. Bind the transaction manager to a specific factory and identify true atomicity boundaries.
6. Test database names, connectivity, data isolation, access permissions, and cross-database failure cases.

**Remember:** Choosing the right `MongoClient` determines the deployment/credentials; `MongoDatabaseFactory` determines the default database; `MongoTemplate` or the repository determines where application operations execute. These three levels must be explicitly linked to prevent writing data to the wrong place.

## References

- [Spring Data MongoDB — Connecting to MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/configuration.html)
- [MongoDatabaseFactory API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoDatabaseFactory.html)
- [SimpleMongoClientDatabaseFactory API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/SimpleMongoClientDatabaseFactory.html)
- [MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html)
- [EnableMongoRepositories API](https://docs.spring.io/spring-data/data-mongodb/reference/api/java/org/springframework/data/mongodb/repository/config/EnableMongoRepositories.html)
